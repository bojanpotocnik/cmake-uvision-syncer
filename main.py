import enum
import operator
import os
import sys
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Union, Iterable, Collection, Set, Tuple, Callable

from lxml import etree

__author__ = "Bojan Potočnik"

fp_cmake = r"G:\Git\Dia-Vit\fw-spectrometer-logger\CMakeLists.txt"
# fp_proj = r"D:\SDK\nRF5_SDK_15.2.0_9412b96\examples\peripheral\twi_scanner\pca10056\blank\arm5_no_packs\twi_scanner_pca10056.uvoptx"
fp_proj = r"G:\Git\Dia-Vit\fw-spectrometer-logger\spectral_data_logger.uvprojx"

UnknownInt = int
UnknownBool = bool


@enum.unique
class FileType(enum.Enum):
    C_SOURCE = 1
    """C Source file"""
    ASM_SOURCE = 2
    """Assembly language file"""
    OBJECT = 3
    """Object file"""
    LIBRARY = 4
    """Library file"""
    TEXT_DOCUMENT = 5
    """Text Document file"""
    CUSTOM = 7
    """Custom file"""
    CPP_SOURCE = 8
    """C++ Source file"""
    IMAGE = 9
    """Image file"""


# region XML data structures for Project File

@dataclass
class Target:
    @dataclass
    class Toolset:
        number: int
        name: str

    @dataclass
    class Compiler:
        cc: str
        ac6: bool

    @dataclass
    class Options:
        @dataclass
        class Common:
            device: str
            vendor: str
            pack_id: str
            pack_url: str
            cpu: str
            device_id: int
            register_file: str

        @dataclass
        class Properties:
            use_cpp_compiler: bool

        common: Common
        properties: Properties

    @dataclass
    class Build:
        @dataclass
        class Misc:
            @dataclass
            class Memory:
                @enum.unique
                class Type(enum.Enum):
                    """TODO: Real meaning unknown."""
                    TYPE0 = 0
                    TYPE1 = 1

                name: str
                type: Type
                start: int
                size: int

            cpu_type: str
            memories: List[Memory]

        @dataclass
        class C:
            optimization: int
            strict: bool
            c99: bool
            gnu: bool
            misc: List[str]
            defines: List[str]
            undefines: List[str]
            include_paths: List[str]

        @dataclass
        class Asm:
            misc: List[str]
            defines: List[str]
            undefines: List[str]
            include_paths: List[str]

        @dataclass
        class Linker:
            text_address_range: int
            data_address_range: int
            misc: List[str]

        misc: Misc
        c: C
        asm: Asm
        ld: Linker

    @dataclass
    class File:
        name: str
        type: FileType
        path: str

    @dataclass
    class Group:
        name: str
        files: List['Target.File']

    name: str
    toolset: Toolset
    compiler: Compiler
    options: Options
    build: Build
    groups: List[Group]


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

    @dataclass
    class File:
        @enum.unique
        class Attribute(enum.Enum):
            CONFIG = "config"

        @enum.unique
        class Category(enum.Enum):
            SOURCE = "source"

        attr: Attribute
        category: Category
        condition: Optional[str]
        name: str
        version: str
        instance: str
        component: 'RTE.Component'
        package: 'RTE.Package'
        target_infos: List['RTE.TargetInfo']

    packages: List[Package]
    components: List[Component]
    files: List[File]


# endregion XML data structures for Project File

# region XML data structures for Project Options file

@dataclass
class File:
    group_number: int
    """Number of the :cls:`Group` this file belongs to."""
    number: int
    """Number of the file (global across all groups)."""
    type: FileType
    """File type as selected in the Options for File ... -> Properties dialog"""
    expanded: bool
    """Whether the file is expanded (include file dependencies shown) in the Project Window file browser."""
    tv_exp_opt_dlg: UnknownBool
    dave2: UnknownBool
    path: str
    filename: str
    rte_flag: bool
    """Whether this file is part of/managed by the Keil MDK Run-Time Environment (RTE) and therefore read-only."""
    shared: UnknownBool

    _project_file: Target.File = None
    """Reference to the instance of this file from the Project File."""


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

    _project_group: Target.Group = None
    """Reference to the instance of this group from the Project File."""


# endregion XML data structures for Project Options file


# region XML parsing helper functions

def text(element: etree.ElementBase, name: str, is_attribute: bool = False, nullable: bool = False) -> Optional[str]:
    if is_attribute:
        if nullable:
            return element.attrib.get(name)
        else:
            return element.attrib[name]

    value = element.xpath(name)

    if (not value) and nullable:
        return None

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
    targets: List[Target]
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

        # noinspection PyCallByClass,SpellCheckingInspection
        targets = [
            Target(
                name=text(target, "TargetName"),
                toolset=Target.Toolset(
                    number=strict_hex(target, "ToolsetNumber"),
                    name=text(target, "ToolsetName")
                ),
                compiler=Target.Compiler(
                    cc=text(target, "pCCUsed"),
                    ac6=strict_bool(target, "uAC6")
                ),
                options=next(
                    # There is always only one package, but using generator is clean and
                    # effective way of creating an inline local variable.
                    Target.Options(
                        common=next(
                            Target.Options.Common(
                                device=text(tco, "Device"),
                                vendor=text(tco, "Vendor"),
                                pack_id=text(tco, "PackID"),
                                pack_url=text(tco, "PackURL"),
                                cpu=text(tco, "Cpu"),
                                device_id=int(text(tco, "DeviceId")),
                                register_file=text(tco, "RegisterFile")
                            ) for tco in to.xpath("TargetCommonOption")
                        ),
                        properties=next(
                            Target.Options.Properties(
                                use_cpp_compiler=strict_bool(tcp, "UseCPPCompiler"),
                            ) for tcp in to.xpath("CommonProperty")
                        )
                    ) for to in target.xpath("TargetOption")
                ),
                build=next(
                    Target.Build(
                        misc=Target.Build.Misc(
                            cpu_type=text(to_taa, "ArmAdsMisc/AdsCpuType"),
                            memories=[
                                Target.Build.Misc.Memory(
                                    name=memory.tag,
                                    type=Target.Build.Misc.Memory.Type(int(text(memory, "Type"))),
                                    start=strict_hex(memory, "StartAddress"),
                                    size=strict_hex(memory, "Size")
                                ) for memory in to_taa.xpath("ArmAdsMisc/OnChipMemories/*")
                            ]
                        ),
                        c=next(
                            Target.Build.C(
                                optimization=int(text(to_taa_c, "Optim")),
                                strict=strict_bool(to_taa_c, "Strict"),
                                c99=strict_bool(to_taa_c, "uC99"),
                                gnu=strict_bool(to_taa_c, "uGnu"),
                                misc=[
                                    mc.strip() for mc in text(to_taa_c, "VariousControls/MiscControls").split(",")
                                ],
                                defines=[
                                    mc.strip() for mc in text(to_taa_c, "VariousControls/Define").split(" ")
                                ],
                                undefines=[
                                    mc.strip() for mc in (text(to_taa_c, "VariousControls/Undefine") or "").split(" ")
                                ],
                                include_paths=[
                                    mc.strip() for mc in text(to_taa_c, "VariousControls/IncludePath").split(";")
                                ]
                            ) for to_taa_c in to_taa.xpath("Cads")
                        ),
                        asm=next(
                            Target.Build.Asm(
                                misc=[
                                    mc.strip() for mc in text(to_taa_a, "VariousControls/MiscControls").split(",")
                                ],
                                defines=[
                                    mc.strip() for mc in text(to_taa_a, "VariousControls/Define").split(" ")
                                ],
                                undefines=[
                                    mc.strip() for mc in (text(to_taa_a, "VariousControls/Undefine") or "").split(" ")
                                ],
                                include_paths=[
                                    mc.strip() for mc in text(to_taa_a, "VariousControls/IncludePath").split(";")
                                ]
                            ) for to_taa_a in to_taa.xpath("Aads")
                        ),
                        ld=next(
                            Target.Build.Linker(
                                text_address_range=strict_hex(to_taa_ld, "TextAddressRange"),
                                data_address_range=strict_hex(to_taa_ld, "DataAddressRange"),
                                misc=[
                                    mc.strip() for mc in
                                    text(to_taa_ld, "Misc").split(",")  # TODO: Delimiter unknown
                                ]
                            ) for to_taa_ld in to_taa.xpath("LDads")
                        )
                    ) for to_taa in target.xpath("TargetOption/TargetArmAds")
                ),
                groups=[
                    Target.Group(
                        name=text(group, "GroupName"),
                        files=[
                            Target.File(
                                name=text(file, "FileName"),
                                type=FileType(int(text(file, "FileType"))),
                                path=text(file, "FilePath")
                            ) for file in group.xpath("Files/File")
                        ]
                    ) for group in target.xpath("Groups/Group")
                ]
            ) for target in xproj.xpath("Targets/Target")
        ]

        # region RTE
        # noinspection PyCallByClass,PyTypeChecker
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
                    package=next(
                        # There is always only one package, but using generator is clean and
                        # effective way of creating an inline local variable.
                        # This new instance of package will be replaced below with reference to an actual matching
                        # instance of the package from rte.packages.
                        RTE.Package(
                            name=text(package, "name", True),
                            url=text(package, "url", True),
                            vendor=text(package, "vendor", True),
                            version=text(package, "version", True),
                            target_infos=None
                        ) for package in component.xpath("package")
                    ),
                    target_infos=[
                        RTE.TargetInfo(
                            name=text(ti, "name", True),
                            # TODO: Handle nullable
                            # RTE.TargetInfo.VersionMatchMode(text(ti, "versionMatchMode", True, True))
                            version_match_mode=None
                        ) for ti in component.xpath("targetInfos/targetInfo")
                    ]
                ) for component in xproj.xpath("RTE/components/component")
            ],
            files=[
                RTE.File(
                    attr=RTE.File.Attribute(text(file, "attr", True)),
                    category=RTE.File.Category(text(file, "category", True)),
                    condition=text(file, "condition", True, True),
                    name=text(file, "name", True),
                    version=text(file, "version", True),
                    instance=text(file, "instance"),
                    component=next(
                        RTE.Component(
                            class_=text(component, "Cclass", True),
                            group=text(component, "Cgroup", True),
                            vendor=text(component, "Cvendor", True),
                            version=text(component, "Cversion", True),
                            condition=text(component, "condition", True),
                            package=None,
                            target_infos=None
                        ) for component in file.xpath("component")
                    ),
                    package=None,  # TODO
                    target_infos=None,  # TODO
                ) for file in xproj.xpath("RTE/files/file")
            ]
        )
        # TODO: Connect actual references of the rte.packages and rte.packages.target_infos
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
        # endregion RTE

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
                        type=FileType(int(text(file, "FileType"))),
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

        # Add RTE files to the file groups to actually match the Project Window file browser.
        for file in rte.files:
            # Find the group to which this file belongs to (there shall be one and only one).
            group = None
            group_number = 1
            for group_number, group in enumerate(groups, 1):
                if group.files and group.files[0].group_number != group_number:
                    warnings.warn(f"Inconsistent group number {group.files[0].group_number} for group {group.name}"
                                  f" (expected to be {group_number})")
                if group.rte_flag and group.name.strip(":") == file.component.class_:
                    break
            group.files.append(File(
                group_number=group_number,
                number=max(f.number for g in groups for f in g.files) + 1,
                type=None,
                expanded=False,
                tv_exp_opt_dlg=False,  # TODO
                dave2=False,  # TODO
                path=file.instance,
                filename=os.path.basename(file.instance),
                rte_flag=True,
                shared=False
            ))

        return cls(
            targets=targets,
            groups=groups
        )


class CMake:
    @enum.unique
    class Language(enum.Enum):
        ASM = "Assembler"
        C = "C"
        CPP = "C++"

    @dataclass
    class String:
        value: str
        """The actual string value."""
        languages: Set['CMake.Language']
        """Set of all build configs in which this value is present."""
        common: bool = False
        comment: Optional[str] = None
        """Comment which will be added to the line before"""

        def __eq__(self, o: 'CMake.String') -> bool:
            if isinstance(o, type(self)):
                return self.value == o.value
            elif isinstance(o, str):
                return self.value == o
            return NotImplemented

    def __init__(self) -> None:
        self.include_paths: List[CMake.String] = []
        self.defines: List[CMake.String] = []
        self.undefines: List[CMake.String] = []
        self.source_file_paths: List[CMake.String] = []

    @classmethod
    def _get(cls, lst: List[String], obj: str) -> String:
        """Get existing object from the list or append a new one to the end."""
        try:
            # noinspection PyTypeChecker
            itm = lst[lst.index(obj)]
        except ValueError:
            # noinspection PyCallByClass
            itm = cls.String(obj, set())
            lst.append(itm)
        return itm

    @classmethod
    def _add_values(cls, where: List[String], values: Union[str, Iterable[str]],
                    languages: Union[Language, Collection[Language]], comment: Optional[str] = None) -> None:
        if isinstance(languages, CMake.Language):
            languages = [languages]

        for val in values:
            obj = cls._get(where, val)
            if comment is not None:
                # Add comment to the first value only
                obj.comment = comment
                comment = None
            obj.languages.update(languages)

    def add_include_paths(self, paths: Union[str, Iterable[str]], languages: Union[Language, Collection[Language]],
                          comment: str = None) -> None:
        if isinstance(paths, (str, Path)):
            paths = [paths]
        self._add_values(self.include_paths, paths, languages, comment)

    def add_defines(self, defines: Union[str, Iterable[str]], languages: Union[Language, Collection[Language]],
                    comment: str = None) -> None:
        self._add_values(self.defines, defines, languages, comment)

    def add_undefines(self, undefines: Union[str, Iterable[str]], languages: Union[Language, Collection[Language]],
                      comment: str = None) -> None:
        self._add_values(self.undefines, undefines, languages, comment)

    def add_source_files(self, paths: Union[str, Iterable[str]], languages: Union[Language, Collection[Language]],
                         comment: str = None) -> None:
        if isinstance(paths, (str, Path)):
            paths = [paths]
        self._add_values(self.source_file_paths, paths, languages, comment)

    def _check_common(self) -> Set[Language]:
        """
        Check which properties are common to all language configurations.

        :return: Set of all used languages (languages with at least one property)
        """
        all_props = (self.include_paths, self.defines, self.undefines, self.source_file_paths)

        # Get all of the defined languages used
        languages = {lang
                     for props in all_props
                     for prop in props
                     for lang in prop.languages}

        for props in all_props:
            for prop in props:
                prop.common = (prop.languages == languages)

        return languages

    def __str__(self) -> str:
        languages = sorted(self._check_common(), key=operator.attrgetter('value'))

        ret_str = []

        # Set of the build properties
        prop_sets: List[Tuple[str, str, List[CMake.String]]] = [
            ("include directories", "INCLUDE_DIRS", self.include_paths),
            ("definitions", "DEFINES", self.defines),
            ("un-defines", "UNDEFINES", self.undefines),
            ("source files", "SOURCES", self.source_file_paths),
        ]

        # Set of the language configs per build property
        sub_prop_sets: List[Tuple[str, str, Callable[[CMake.String], bool]]] = [
            ("Common", "COMMON", lambda prop: prop.common),
            *((lang.value + " specific", lang.name,
               lambda prop, lang_=lang: (not prop.common) and (lang_ in prop.languages))
              for lang in languages)
        ]

        for section_comment, section_var_prefix, section_props in prop_sets:
            ss_str = []
            for comment, var_suffix, filter_fun in sub_prop_sets:
                s = (f"# {comment} {section_comment}\n"
                     f"set({section_var_prefix}_{var_suffix}")
                for ip in filter(filter_fun, section_props):
                    if ip.comment is not None:
                        s += f"\n\t# {ip.comment}"
                    s += f"\n\t{ip.value}"
                s += "\n)"
                ss_str.append(s)
            ret_str.append("\n\n".join(ss_str))

        # for lang, lc in self.language_configs.items():
        #     s = (f"# {lang.value} include directories\n"
        #          f"set(INCLUDE_DIRS_{lang.name}"
        #          )
        #     for ip in lc.include_paths:
        #         s += f"\n\t{ip}"
        #     s += "\n)"
        #     lc_str.append(s)

        return "\n\n\n".join(ret_str)


def main() -> None:
    uvpf = UVisionProject.new(fp_proj)

    # print("ASM Includes:")
    # print("".join(f"\t{path}\n" for path in uvpf.targets[0].build.asm.include_paths))
    #
    # print("C Includes:")
    # print("".join(f"\t{path}\n" for path in uvpf.targets[0].build.c.include_paths))

    print()

    # for group in uvpf.targets[0].groups:
    #     for file in group.files:
    #         if "ads1x1x" not in file.name:
    #             continue
    #         print(file)
    #
    # for group in uvpf.groups:
    #     for file in group.files:
    #         if "ads1x1x" not in file.filename:
    #             continue
    #         print(file)

    cmake = CMake()

    cmake.add_include_paths(uvpf.targets[0].build.asm.include_paths, CMake.Language.ASM)
    cmake.add_defines(uvpf.targets[0].build.asm.defines, CMake.Language.ASM)
    cmake.add_undefines(uvpf.targets[0].build.asm.undefines, CMake.Language.ASM)
    # cmake.add_undefines(uvpf.targets[0].groups, CMake.Language.ASM)

    cmake.add_include_paths(uvpf.targets[0].build.c.include_paths, CMake.Language.C)
    cmake.add_defines(uvpf.targets[0].build.c.defines, CMake.Language.C)
    cmake.add_undefines(uvpf.targets[0].build.c.undefines, CMake.Language.C)

    for group in uvpf.groups:
        comment = group.name
        # TODO: Add one comment for every file type as they are in the separate sections
        for file in group.files:
            if file.type == FileType.ASM_SOURCE:
                lang = CMake.Language.ASM
            elif file.type == FileType.C_SOURCE:
                lang = CMake.Language.C
            elif file.type == FileType.TEXT_DOCUMENT:
                print(f"Text file: {file}", file=sys.stderr)
                continue
            else:
                warnings.warn(f"Unsupported file type: {file.type} for {file}")
                if file.rte_flag and file.filename.endswith(".c"):
                    lang = CMake.Language.C
                elif file.rte_flag and file.filename.endswith(".s"):
                    lang = CMake.Language.ASM
                else:
                    continue
            cmake.add_source_files(file.path, lang, comment)
            comment = None

    print(cmake)


if __name__ == "__main__":
    main()
