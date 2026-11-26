import os, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
from tools import openrouter_adapter as router
from tools import groq_adapter as groq

class Routing(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(patch.stopall)
        patch.object(groq,"STATE",Path(self.tmp.name)/"groq.json").start()
        patch.object(groq,"BLOCKS",{}).start()
        patch.object(groq,"CALLS",0).start()
        patch.dict(os.environ,{"GROQ_API_KEY":"fixture","GOAT_GROQ_FREE_ONLY":"1"}).start()
    def test_daily_openrouter_block_does_not_stop_groq(self):
        with patch.object(router,"_openrouter_status",return_value={"status":"waiting_provider","retry_after":85000}):
            self.assertEqual(router.provider_status()["provider"],"groq")
            router.require_available()
        with patch.object(groq,"request",return_value='{"ok":true}') as request:
            self.assertTrue(router.gerar_json([{"text":"fixture"}])["ok"])
            self.assertEqual(request.call_args.args[0],groq.MODELS_TEXT[0])
    def test_fallback(self):
        with patch.object(groq,"request",side_effect=router.ProviderUnavailable("429",429)), patch.object(router,"_gerar_openrouter",return_value='{"ok":false}') as backup:
            self.assertFalse(router.gerar_json([{"text":"fixture"}])["ok"])
            backup.assert_called_once()
    def test_vision_and_no_silent_dropping(self):
        img={"inline_data":{"mime_type":"image/jpeg","data":"fixture"}}
        with patch.object(groq,"request",return_value='{"ok":false}') as request:
            router.gerar_json([img])
            self.assertEqual(request.call_args.args[0],groq.MODEL_VISION)
        with patch.object(groq,"request") as request, patch.object(router,"_gerar_openrouter",return_value='{"ok":false}') as backup:
            with self.assertRaisesRegex(ValueError,"três imagens"):
                router.gerar_json([img]*4)
            request.assert_not_called()
            backup.assert_not_called()
        with patch.object(groq,"request",return_value='{"ok":true}') as request:
            router.gerar_json([img]*3)
            self.assertEqual(len(request.call_args.args[1]),3)
    def test_per_model_cooldown(self):
        groq.block(groq.MODELS_TEXT[0],60)
        self.assertEqual(groq.candidates(),[groq.MODELS_TEXT[1]])
        self.assertTrue(groq.candidates(True))
    def test_unconfigured(self):
        with patch.dict(os.environ,{"GOAT_GROQ_FREE_ONLY":"0"}):
            self.assertFalse(groq.available())

if __name__=="__main__":
    unittest.main()
