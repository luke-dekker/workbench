// Workbench: one-shot (and re-runnable) project setup for the fast loop.
//
//   menu:      Workbench > Setup project
//   headless:  Unity.exe -batchmode -nographics -projectPath <root> -executeMethod Workbench.Setup.Headless
//              (no -quit: package import triggers a domain reload, so this script exits the editor itself
//               once everything has settled; see Resume())
//
// What it does, all idempotent:
//   - Enter Play Mode Options on, domain reload + scene reload OFF  (play starts in well under a second)
//   - text serialization + visible meta files                       (git-friendly)
//   - Android: IL2CPP, ARM64, min API 24, identifier com.workbench.<product>  (what ARCore needs)
//   - Assets/Scenes/Bootstrap.unity exists, is in Build Settings, and is the play-mode start scene
//   - adds the packages in Packages[] through the Package Manager (versions resolved for this editor)
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEditor.Build;
using UnityEditor.PackageManager;
using UnityEditor.PackageManager.Requests;
using UnityEditor.SceneManagement;
using UnityEngine;

namespace Workbench
{
    [InitializeOnLoad]
    public static class Setup
    {
        public const string BootstrapScene = "Assets/Scenes/Bootstrap.unity";

        // Package Manager picks the newest version that this editor supports.
        static readonly string[] Packages =
        {
            "com.unity.xr.arfoundation",     // AR Foundation (includes XR Simulation for in-editor AR)
            "com.unity.xr.arcore",           // Android AR provider
            "com.unity.cloud.gltfast",       // glTF import/export, Apache-2.0: the Godot exchange format
            "com.unity.inputsystem",         // AR Foundation samples assume it
            "com.unity.ide.visualstudio",    // .csproj generation for the MIT C# extension in VS Code
            "com.unity.test-framework",
            "com.unity.ugui",
        };

        const string KeyPending = "wb.setup.pending";   // SessionState: a headless run is in flight

        static Setup()
        {
            // We land here again after the domain reload that package import causes.
            if (SessionState.GetBool(KeyPending, false))
                EditorApplication.delayCall += Resume;
        }

        [MenuItem("Workbench/Setup project")]
        public static void Apply()
        {
            ApplySettings();
            EnsureBootstrapScene();
            AddPackages();
        }

        public static void Headless()
        {
            SessionState.SetBool(KeyPending, true);
            ApplySettings();
            EnsureBootstrapScene();
            var missing = Missing();
            if (missing.Length == 0) { Finish(0, "all packages present"); return; }
            var req = Client.AddAndRemove(missing);
            Log("adding " + string.Join(", ", missing) + " ...");
            while (!req.IsCompleted) System.Threading.Thread.Sleep(100);
            if (req.Status == StatusCode.Failure) { Finish(1, "package add failed: " + (req.Error != null ? req.Error.message : "?")); return; }
            Log("packages resolved; waiting for import + compile, then exiting");
            // Normally a domain reload follows and Resume() exits. If nothing recompiles, exit after things go quiet.
            _quietSince = EditorApplication.timeSinceStartup;
            EditorApplication.update += ExitWhenQuiet;
        }

        // ------------------------------------------------------------------ settings
        static void ApplySettings()
        {
            EditorSettings.serializationMode = SerializationMode.ForceText;
            VersionControlSettings.mode = "Visible Meta Files";
            EditorSettings.enterPlayModeOptionsEnabled = true;
            EditorSettings.enterPlayModeOptions = EnterPlayModeOptions.DisableDomainReload
                                                | EnterPlayModeOptions.DisableSceneReload;

            var product = string.IsNullOrWhiteSpace(PlayerSettings.productName)
                ? new DirectoryInfo(Path.GetDirectoryName(Application.dataPath)).Name
                : PlayerSettings.productName;
            PlayerSettings.productName = product;
            if (string.IsNullOrWhiteSpace(PlayerSettings.companyName) || PlayerSettings.companyName == "DefaultCompany")
                PlayerSettings.companyName = "workbench";

            var android = NamedBuildTarget.Android;
            var slug = new string(product.ToLowerInvariant().Where(char.IsLetterOrDigit).ToArray());
            if (string.IsNullOrEmpty(slug)) slug = "app";
            PlayerSettings.SetApplicationIdentifier(android, "com.workbench." + slug);
            PlayerSettings.SetScriptingBackend(android, ScriptingImplementation.IL2CPP);
            PlayerSettings.Android.targetArchitectures = AndroidArchitecture.ARM64;
            if ((int)PlayerSettings.Android.minSdkVersion < 24)
                PlayerSettings.Android.minSdkVersion = (AndroidSdkVersions)24;

            AssetDatabase.SaveAssets();
            Log("settings applied: play-mode options (no domain/scene reload), text serialization, Android IL2CPP/ARM64/API24, id com.workbench." + slug);
        }

        static void EnsureBootstrapScene()
        {
            Directory.CreateDirectory(Path.GetDirectoryName(BootstrapScene));
            if (!File.Exists(BootstrapScene))
            {
                var scene = EditorSceneManager.NewScene(NewSceneSetup.DefaultGameObjects, NewSceneMode.Single);
                new GameObject("Bootstrap");   // put session / XR startup components here
                EditorSceneManager.SaveScene(scene, BootstrapScene);
                Log("created " + BootstrapScene);
            }
            var scenes = EditorBuildSettings.scenes.ToList();
            if (!scenes.Any(s => s.path == BootstrapScene))
            {
                scenes.Insert(0, new EditorBuildSettingsScene(BootstrapScene, true));
                EditorBuildSettings.scenes = scenes.ToArray();
            }
            EditorSceneManager.playModeStartScene = AssetDatabase.LoadAssetAtPath<SceneAsset>(BootstrapScene);
            AssetDatabase.SaveAssets();
        }

        // ------------------------------------------------------------------ packages
        static string[] Missing()
        {
            var list = Client.List(true, true);
            while (!list.IsCompleted) System.Threading.Thread.Sleep(50);
            var have = new HashSet<string>(list.Result.Select(p => p.name));
            return Packages.Where(p => !have.Contains(p)).ToArray();
        }

        static AddAndRemoveRequest _menuReq;
        static void AddPackages()
        {
            var missing = Missing();
            if (missing.Length == 0) { Log("all packages present"); return; }
            Log("adding " + string.Join(", ", missing));
            _menuReq = Client.AddAndRemove(missing);
            EditorApplication.update += PollMenu;
        }

        static void PollMenu()
        {
            if (_menuReq == null || !_menuReq.IsCompleted) return;
            EditorApplication.update -= PollMenu;
            if (_menuReq.Status == StatusCode.Failure) Debug.LogError("[Workbench] package add failed: " + (_menuReq.Error != null ? _menuReq.Error.message : "?"));
            else Log("packages added");
            _menuReq = null;
        }

        // ------------------------------------------------------------------ headless exit
        static double _quietSince;
        static void ExitWhenQuiet()
        {
            if (EditorApplication.isCompiling || EditorApplication.isUpdating)
            {
                _quietSince = EditorApplication.timeSinceStartup;
                return;
            }
            if (EditorApplication.timeSinceStartup - _quietSince > 5.0)
            {
                EditorApplication.update -= ExitWhenQuiet;
                Resume();
            }
        }

        static void Resume()
        {
            if (EditorApplication.isCompiling || EditorApplication.isUpdating)
            {
                EditorApplication.delayCall += Resume;
                return;
            }
            var missing = Missing();
            if (missing.Length == 0) Finish(0, "setup complete");
            else Finish(1, "still missing after import: " + string.Join(", ", missing));
        }

        static void Finish(int code, string msg)
        {
            SessionState.EraseBool(KeyPending);
            AssetDatabase.SaveAssets();
            if (code == 0) Log(msg); else Debug.LogError("[Workbench] " + msg);
            if (Application.isBatchMode) EditorApplication.Exit(code);
        }

        static void Log(string msg) { Debug.Log("[Workbench] " + msg); }
    }
}
