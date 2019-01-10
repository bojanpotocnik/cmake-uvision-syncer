import enum
import os
import warnings
from dataclasses import dataclass
from typing import List, Any, Optional

from lxml import etree

__author__ = "Bojan Potočnik"

fp_cmake = r"<machine local, not commited>\CMakeLists.txt"
fp_proj = r"<machine local, not commited>\twi_scanner_pca10056.uvprojx"

UnknownInt = int
UnknownBool = bool
TODOType = Any


# region XML data structures for Project File

@dataclass
class Target:
    @dataclass
    class Toolset:
        number: int
        name: str

    @dataclass
    class Options:
        pass

    name: str
    toolset: Toolset


@dataclass
class RTE:
    @dataclass
    class TargetInfo:
        @enum.unique
        class VersionMatchMode(enum.Enum):
            FIXED = "fixed"

        name: str
        version_match_mode: Optional[VersionMatchMode]

    @dataclass
    class Package:
        name: str
        url: str
        vendor: str
        version: str
        target_infos: List['RTE.TargetInfo']

    @dataclass
    class Component:
        class_: str
        group: str
        vendor: str
        version: str
        condition: str
        package: 'RTE.Package'
        target_infos: List['RTE.TargetInfo']

    packages: List[Package]
    components: List[Component]
    files: TODOType


# endregion XML data structures for Project File

# region XML data structures for Project Options file

@dataclass
class File:
    group_number: int
    """Number of the :cls:`Group` this file belongs to."""
    number: int
    """Number of the file (global across all groups)."""
    type: UnknownInt
    expanded: UnknownBool
    """Whether the file is expanded (include file dependencies shown) in the Project Window file browser."""
    tv_exp_opt_dlg: UnknownBool
    dave2: UnknownBool
    path: str
    filename: str
    rte_flag: bool
    """Whether this file is part of/managed by the Keil MDK Run-Time Environment (RTE) and therefore read-only."""
    shared: UnknownBool


@dataclass
class Group:
    name: str
    """Group name as shown in the Project Window file browser."""
    expanded: bool
    """Whether the group is expanded (files shown) in the Project Window file browser."""
    tv_exp_opt_dlg: UnknownBool
    cb_sel: UnknownBool
    rte_flag: bool
    """Whether this group is part of/managed by the Keil MDK Run-Time Environment (RTE) and therefore read-only."""
    files: List[File]
    """List of files in this group."""


# endregion XML data structures for Project Options file


# region XML parsing helper functions

def text(element: etree.ElementBase, name: str, is_attribute: bool = False) -> str:
    if is_attribute:
        return element.attrib[name]

    value = element.xpath(name)
    if len(value) != 1:
        raise ValueError(f"Only one '{name}' tag per tree is supported, {len(value)}  found")
    return value[0].text


def strict_bool(element: etree.ElementBase, name: str) -> bool:
    value = text(element, name)
    if value == "0":
        return False
    if value == "1":
        return True
    raise ValueError(f"'{value}' (of {name}) is not valid boolean value")


def strict_hex(element: etree.ElementBase, name: str) -> int:
    value = text(element, name)
    if not value.startswith("0x"):
        raise ValueError(f"'{value}' (of {name}) is not valid hexadecimal value")
    return int(value, 16)


# endregion XML parsing helper functions


@dataclass
class UVisionProject:
    # region Project File
    # endregion Project File

    # region Project Options
    groups: List[Group]
    """Groups of files, as shown in the Project Window file browser."""

    # endregion Project Options

    @classmethod
    def new(cls, project_file_path: str) -> 'UVisionProject':
        fp_base = os.path.splitext(project_file_path)[0]

        with open(fp_base + ".uvprojx") as f:
            # noinspection PyProtectedMember
            xproj: etree._Element = etree.parse(f).getroot()

        with open(fp_base + ".uvoptx") as f:
            # noinspection PyProtectedMember
            xopt: etree._Element = etree.parse(f).getroot()

        # region Project File
        if xproj.tag != "Project":
            raise ValueError("Invalid uVision Project File XML file")

        target = xproj.xpath("/Project/Targets/Target")
        if len(target) > 1:
            warnings.warn(f"Parsing of multiple ({len(target)}) targets not yet supported")
        target = target[0]

        # noinspection PyCallByClass
        target = Target(
            name=text(target, "TargetName"),
            toolset=Target.Toolset(
                number=strict_hex(target, "ToolsetNumber"),
                name=text(target, "ToolsetName")
            )
        )

        # noinspection PyCallByClass
        rte = RTE(
            packages=[
                RTE.Package(
                    name=text(package, "name", True),
                    url=text(package, "url", True),
                    vendor=text(package, "vendor", True),
                    version=text(package, "version", True),
                    target_infos=[
                        RTE.TargetInfo(
                            name=text(ti, "name", True),
                            version_match_mode=RTE.TargetInfo.VersionMatchMode(text(ti, "versionMatchMode", True))
                        ) for ti in package.xpath("targetInfos/targetInfo")
                    ]
                ) for package in xproj.xpath("RTE/packages/package")
            ],
            components=[
                RTE.Component(
                    class_=text(component, "Cclass", True),
                    group=text(component, "Cgroup", True),
                    vendor=text(component, "Cvendor", True),
                    version=text(component, "Cversion", True),
                    condition=text(component, "condition", True),
                    package=[
                        # There is always only one package, but using list comprehension [][0] is clean and
                        # effective ways of creating an inline local variable.
                        # This new instance of package will be replaced below with reference to an actual matching
                        # instance of the package from rte.packages.
                        RTE.Package(
                            name=text(package, "name", True),
                            url=text(package, "url", True),
                            vendor=text(package, "vendor", True),
                            version=text(package, "version", True),
                            target_infos=None
                        ) for package in component.xpath("package")
                    ][0],
                    target_infos=[
                        RTE.TargetInfo(
                            name=text(ti, "name", True),
                            version_match_mode=RTE.TargetInfo.VersionMatchMode(text(ti, "versionMatchMode", True))
                        ) for ti in component.xpath("targetInfos/targetInfo")
                    ]
                ) for component in xproj.xpath("RTE/components/component")
            ],
            files=None
        )
        for component in rte.components:
            cp = component.package
            component.package = None
            cp.target_infos = None
            for package in rte.packages:
                # Temporally remove target_infos to enable usage of equality operator.
                pti = package.target_infos
                package.target_infos = None
                if cp == package:
                    component.package = package
                    package.target_infos = pti
                    break
                package.target_infos = pti

        print()

        # endregion Project File

        # region Project Options
        if xopt.tag != "ProjectOpt":
            raise ValueError("Invalid uVision Project Options XML file")

        groups: List[Group] = [
            Group(
                name=text(group, "GroupName"),
                expanded=strict_bool(group, "tvExp"),
                tv_exp_opt_dlg=strict_bool(group, "tvExpOptDlg"),
                cb_sel=strict_bool(group, "cbSel"),
                rte_flag=strict_bool(group, "RteFlg"),
                files=[
                    File(
                        group_number=int(text(file, "GroupNumber")),
                        number=int(text(file, "FileNumber")),
                        type=int(text(file, "FileType")),
                        expanded=strict_bool(file, "tvExp"),
                        tv_exp_opt_dlg=strict_bool(file, "tvExpOptDlg"),
                        dave2=strict_bool(file, "bDave2"),
                        path=text(file, "PathWithFileName"),
                        filename=text(file, "FilenameWithoutPath"),
                        rte_flag=strict_bool(file, "RteFlg"),
                        shared=strict_bool(file, "bShared")
                    ) for file in group.xpath("File")
                ]
            ) for group in xopt.xpath("Group")
        ]

        # There is no more *currently relevant* data in the Project Options file.

        # endregion Project Options

        return cls(
            groups=groups
        )


uvpf = UVisionProject.new(fp_proj)


def main() -> None:
    pass


if __name__ == "__main__":
    main()
