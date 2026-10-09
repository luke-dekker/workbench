# <project> (Unity + Godot mirror)

Scaffolded by `wb new`. Layout:

    Assets/            Unity project (this folder is the Unity project root)
    Assets/Shared  ->  junction to ../shared
    godot/             Godot mirror; godot/shared -> junction to ../shared
    shared/            exchange folder: glTF, textures, audio. Edit here once, both engines see it.
    Builds/            output of Workbench > Build (git-ignored); Builds/last_build.json = what was built

Workbench menu in Unity: Setup project, Build Android/Windows (dev), Play from Bootstrap.
From the shell: `wb open <project> setup|build|deploy|godot|godot_run`. See workbench/docs/FAST_LOOP.md.
