// Workbench: builds from the menu or headless, same code path.
//
//   menu:      Workbench > Build Android / Build Windows
//   headless:  Unity.exe -batchmode -nographics -projectPath <root> -buildTarget Android -executeMethod Workbench.Builder.Android
//              (`wb unity <project> build [android|windows]` wraps this)
//
// Output lands in Builds/<target>/ and Builds/last_build.json records what was built so `wb` can
// install and launch it without parsing ProjectSettings. Development builds by default: they
// carry the player log and allow the debugger / live-tuning channel; the *Release methods are
// for a shipping build.
using System;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEditor.Build;
using UnityEditor.Build.Reporting;
using UnityEngine;

namespace Workbench
{
    public static class Builder
    {
        [MenuItem("Workbench/Build Android (dev)")]
        public static void Android() { Build(BuildTarget.Android, "android", ".apk", true); }

        [MenuItem("Workbench/Build Windows (dev)")]
        public static void Windows() { Build(BuildTarget.StandaloneWindows64, "windows", ".exe", true); }

        public static void AndroidRelease() { Build(BuildTarget.Android, "android", ".apk", false); }
        public static void WindowsRelease() { Build(BuildTarget.StandaloneWindows64, "windows", ".exe", false); }

        static void Build(BuildTarget target, string folder, string ext, bool development)
        {
            var scenes = EditorBuildSettings.scenes.Where(s => s.enabled).Select(s => s.path).ToArray();
            if (scenes.Length == 0 && File.Exists(Setup.BootstrapScene)) scenes = new[] { Setup.BootstrapScene };
            if (scenes.Length == 0)
            {
                Fail("no scenes in Build Settings and no " + Setup.BootstrapScene + "; run Workbench > Setup project");
                return;
            }
            var product = string.IsNullOrWhiteSpace(PlayerSettings.productName) ? "app" : PlayerSettings.productName;
            var root = Path.GetDirectoryName(Application.dataPath);
            var outDir = Path.Combine(root, "Builds", folder);
            Directory.CreateDirectory(outDir);
            var outPath = Path.Combine(outDir, product + ext);

            var opts = new BuildPlayerOptions
            {
                scenes = scenes,
                locationPathName = outPath,
                target = target,
                options = development ? (BuildOptions.Development | BuildOptions.AllowDebugging) : BuildOptions.None,
            };
            Debug.Log("[Workbench] building " + target + " -> " + outPath + " (" + scenes.Length + " scene(s), " + (development ? "dev" : "release") + ")");
            var report = BuildPipeline.BuildPlayer(opts);
            var ok = report.summary.result == BuildResult.Succeeded;
            var group = BuildPipeline.GetBuildTargetGroup(target);
            var identifier = PlayerSettings.GetApplicationIdentifier(NamedBuildTarget.FromBuildTargetGroup(group));
            File.WriteAllText(Path.Combine(root, "Builds", "last_build.json"),
                "{\n" +
                "  \"ok\": " + (ok ? "true" : "false") + ",\n" +
                "  \"target\": \"" + target + "\",\n" +
                "  \"path\": \"" + outPath.Replace("\\", "/") + "\",\n" +
                "  \"identifier\": \"" + identifier + "\",\n" +
                "  \"product\": \"" + product + "\",\n" +
                "  \"development\": " + (development ? "true" : "false") + ",\n" +
                "  \"seconds\": " + report.summary.totalTime.TotalSeconds.ToString("F0") + ",\n" +
                "  \"errors\": " + report.summary.totalErrors + ",\n" +
                "  \"time\": \"" + DateTime.Now.ToString("s") + "\"\n" +
                "}\n");
            if (ok)
            {
                Debug.Log("[Workbench] build ok: " + outPath + " in " + report.summary.totalTime.TotalSeconds.ToString("F0") + "s, " + (report.summary.totalSize / 1000000) + " MB");
                if (Application.isBatchMode) EditorApplication.Exit(0);
            }
            else Fail("build " + report.summary.result + " with " + report.summary.totalErrors + " error(s)");
        }

        static void Fail(string msg)
        {
            Debug.LogError("[Workbench] " + msg);
            if (Application.isBatchMode) EditorApplication.Exit(1);
        }
    }
}
