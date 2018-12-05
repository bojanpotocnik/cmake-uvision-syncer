# CMake ⇄ µVision Synchronizer

For ARM embedded firmware development I commonly use [CLion](https://www.jetbrains.com/clion/) 
in combination with the [Keil µVision®](http://www2.keil.com/mdk5/uvision/).

In my opinion,  
**CLion** is one of the best C/C++ IDEs available - user friendly yet powerful and packed with useful features.
However when considering the embedded targets, the amount of additional configuration required and lack of native 
debugging support becomes noticeable.  
On the other hand, **Keil® MDK**  is one of the most comprehensive software development solution for Arm®-based 
microcontrollers, integrating powerful, feature rich compiler and debugger.

CLion uses [CMake](https://cmake.org/) based project configuration system (using _CMakeLists.txt_ as a main 
project configuration file) while _µVision5_ uses
 [its own file types](http://www.keil.com/support/man/docs/uv4/uv4_b_filetypes.htm) - 
 _.uvprojx_ project file in combination with _.uvoptx_ project options file, both in XML format.

To take the advantage of CLion advanced intelligent coding assistance and code analysis features it is important
that the project parameters (source and include files/directories, project preprocessor definitions, 
compiler and linker flags, ...) in all project files are the same.
If something relevant is changed in the CMake file, uvprojx/uvoptx files shall also be modified accordingly - 
the same is true in both directions.

As such "synchronization" is time consuming and error-prone, the goal of this tool is to automate the process.
