// Workbench: pressing Play always starts from the bootstrap scene, whatever scene is open in the
// editor. Toggle with Workbench > Play from Bootstrap.
//
// Note on Enter Play Mode Options (domain reload off): static fields keep their values between
// plays. Reset them explicitly:
//
//     [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.SubsystemRegistration)]
//     static void ResetStatics() { _instance = null; }
//
// and unsubscribe static event handlers the same way.
using UnityEditor;
using UnityEditor.SceneManagement;

namespace Workbench
{
    [InitializeOnLoad]
    public static class PlayFrom
    {
        const string MenuPath = "Workbench/Play from Bootstrap";
        const string Key = "wb.playFromBootstrap";

        static PlayFrom()
        {
            EditorApplication.delayCall += Sync;
        }

        [MenuItem(MenuPath)]
        static void Toggle()
        {
            EditorPrefs.SetBool(Key, !EditorPrefs.GetBool(Key, true));
            Sync();
        }

        [MenuItem(MenuPath, true)]
        static bool Validate()
        {
            Menu.SetChecked(MenuPath, EditorPrefs.GetBool(Key, true));
            return true;
        }

        static void Sync()
        {
            var on = EditorPrefs.GetBool(Key, true);
            var scene = AssetDatabase.LoadAssetAtPath<SceneAsset>(Setup.BootstrapScene);
            EditorSceneManager.playModeStartScene = (on && scene != null) ? scene : null;
        }
    }
}
