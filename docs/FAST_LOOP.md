# Fast loop: Unity + Godot iteration from the workbench

Goal: make "change a thing, see it running" as short as possible for a Unity + Godot project
(Unity deliverables, Godot mirror) without proprietary helpers. Everything here is
driven from `wb` and the Workbench window; the engine projects stay plain.

Started 2026-10-07. Status legend: `[x]` done and verified, `[~]` written but unverified,
`[ ]` not started.

## TODO (the visible list)

### Unity loop
- [x] Unity project template (`templates/unity/`): Editor scripts, bootstrap scene folder, .gitignore,
      .gitattributes (LFS + UnityYAMLMerge), EditorConfig. `Packages/manifest.json` is generated from the
      built-in modules the installed editor ships (Unity 6 dropped `com.unity.modules.vr`; a fixed list broke).
- [x] `wb new unity-app` scaffolds from the template, creates `godot/` mirror + `shared/` junctions, `git init`.
- [x] `Setup.cs`: one headless pass that adds packages (AR Foundation, ARCore, glTFast, Input System),
      turns on Enter Play Mode Options (no domain/scene reload), text serialization, visible meta files,
      creates `Assets/Scenes/Bootstrap.unity` and sets it as the play-mode start scene.
- [x] `wb open unity-app setup` re-runs Setup headless (idempotent).
- [x] `Builder.cs`: `Workbench > Build Android/Windows` menu items + static methods for the CLI. Output `Builds/`.
- [x] `wb open unity-app build [android|windows]` runs Builder headless, log to `logs/unity-unity-app.log`.
      Verified 2026-10-07: `wb new unity-app` setup pass 164 s (AR Foundation + ARCore 6.6.2, glTFast 6.20,
      Input System 1.20), `wb unity unity-app build windows` 134 s -> Builds/windows/unity-app.exe (dev, 232 MB).
- [~] `wb open unity-app deploy`: build + `adb install -r` + launch + logcat tab. Code written; cannot run
      until the Android module is installed (see Blockers).
- [ ] Assembly definitions in the template (`Assets/Scripts/Game.asmdef`, `Assets/Editor/Workbench.asmdef`)
      so a script edit recompiles one assembly. Setup.cs can create them; not done yet.
- [ ] XR Simulation environment in the bootstrap scene (AR Foundation's in-editor AR; free) so most
      iterations never touch a phone.
- [ ] XR Plug-in Management: enable the ARCore loader for Android (and XR Simulation for the editor)
      from Setup.cs; today it is a manual tick in Project Settings > XR Plug-in Management.
- [ ] Consider URP (Unity 6 default; AR Foundation samples assume it). The template is built-in RP for now.
- [ ] Unity scene files (`.unity`) listed in the Workbench window next to notebooks; opening one starts the
      editor on that scene. (Unity has no clean "open this scene" CLI flag; needs an EditorPrefs handoff
      or a `-executeMethod` that loads the scene.)

### Godot loop
- [x] `.tscn` scenes show up in the Workbench window under their project; double-click runs the scene
      directly (`godot --path <proj> <scene>`), no editor.
- [x] `wb open <project> godot_run [scene]` from the shell.
- [ ] Godot headless export from `wb` (`--headless --export-release <preset>`), needs export templates
      installed (Editor > Manage Export Templates) and a preset in `export_presets.cfg`.
- [ ] Godot Android remote deploy (built in: Remote Debug + USB deploy) documented as the fast path for
      device checks.

### Shared assets (Unity <-> Godot)
- [x] `shared/` folder at the project root; `Assets/Shared` and `godot/shared` are junctions to it.
      Unity's `.meta` and Godot's `.import` sidecars both land in `shared/` and are harmless to the other engine.
- [ ] Blender save handler that re-exports glTF into `shared/` (sceneforge's Blender bridge is the start).
- [ ] `scene.json` (sceneforge GeoPose) -> Unity prefab layout + Godot `.tscn` exporter. Paired Reality
      needs this anyway.
- [ ] glTF round-trip proof: one asset through Blender -> shared/ -> both engines, screenshots compared.

### Workbench integration
- [x] Registry: `unity-app` artifacts (builds, Unity log, logcat) visible via `catalog.show("unity-app")`.
- [ ] Live tuning channel: tiny WebSocket listener in dev builds of both engines + a marimo snippet that
      pushes parameters / catalog data into the running scene. No rebuild to tweak a value.
- [ ] Pure C# game logic in a plain .NET class library tested with `dotnet test` outside Unity.
- [ ] `wb doctor` checks: Android module, adb, Godot export templates, git-lfs.

### Blockers / decisions
- Unity 6000.6.4f1 is installed with only WebGL + Windows Standalone modules. **Android Build Support
  (+ OpenJDK + SDK/NDK) must be added in Unity Hub** before `build android` / `deploy` can run.
  That also provides `adb` (`.../PlaybackEngines/AndroidPlayer/SDK/platform-tools/adb.exe`).
- No test phone/headset has been plugged in yet; `deploy` is unverified end to end.
- VS Code: the base C# extension is MIT; Microsoft's C# Dev Kit is **not** OSI licensed. Use the base
  extension (+ Unity's `com.unity.ide.visualstudio` package for project generation).
- Godot phone AR (ARCore) is a community plugin of uneven maintenance. The Godot mirror targets
  known-pose rendering + OpenXR.
- Unity Hot Reload and AR Foundation Remote are paid/proprietary: not used. Enter Play Mode Options
  + asmdefs + XR Simulation are the free equivalents.

## How the pieces fit

    workbench/
      templates/unity/         copied by `wb new <project>` when kind = "unity"
        Assets/Editor/Workbench/Setup.cs     headless project setup (packages, play-mode options, bootstrap scene)
        Assets/Editor/Workbench/Builder.cs   builds (menu + CLI)
        Assets/Editor/Workbench/PlayFrom.cs  play always starts from Bootstrap.unity
        .gitignore / .gitattributes / .editorconfig
      templates/godot/         minimal Godot 4 project for the mirror (project.godot + main.tscn)
      wb/unity.py              scaffold, headless runs, adb, deploy
      wb/launch.py             `setup`, `build`, `deploy`, `godot_run` tools; .tscn as a runnable "scene"

    <unity-app root>/           = the Unity project (ProjectSettings/, Assets/, Packages/)
      Assets/Shared  -> junction -> shared/
      godot/                   Godot mirror project; godot/shared -> junction -> shared/
      shared/                  canonical exchange folder (glTF, textures, audio)
      Builds/                  apk / exe from Builder (git-ignored)

## Commands

    wb new unity-app                      # scaffold + run Setup headless (first run: a few minutes)
    wb new unity-app --no-setup           # scaffold only
    wb open unity-app unity               # editor
    wb open unity-app setup               # re-run Setup.cs headless
    wb open unity-app build               # Android apk -> Builds/ (needs Android module)
    wb open unity-app build windows       # Windows exe -> Builds/
    wb open unity-app deploy              # build + adb install + launch + logcat tab
    wb open unity-app godot               # Godot editor on godot/
    wb open unity-app godot_run           # run godot/ main scene, no editor
    wb open sceneforge godot_run scenes/x.tscn

Unity headless invocations log to `logs/unity-<project>.log`; the terminal shows the tail on failure.

## Why these choices
- Enter Play Mode Options (disable domain + scene reload) is the single largest speedup Unity offers
  for free: play starts in well under a second instead of several. The cost is that static state
  survives between plays; `PlayFrom.cs` documents the `[RuntimeInitializeOnLoadMethod]` reset pattern.
- Headless batchmode means the build never needs the editor open, so the editor can stay in play mode
  with XR Simulation while a device build runs in the background.
- Godot's `--path <proj> <scene>` starts a scene in well under a second; the editor is optional.
- Junctions, not copies: one canonical `shared/`, both engines see it live.
