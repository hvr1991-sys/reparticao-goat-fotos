import copy, unittest, tempfile, base64, io
from pathlib import Path
from unittest.mock import patch
from PIL import Image
import compositor_v2 as c

def fixture():
    return dict(tipo="composicao_livre",ilustrativo=True,elementos=[
        dict(tipo="forma",x=0,y=0,w=1080,h=1350,cor="preto"),
        dict(tipo="texto",papel="titulo",texto="TESTE GOAT",x=60,y=900,w=960,h=150,tamanho=110,cor="amarelo"),
        dict(tipo="marca",x=475,y=1150,w=130,h=80)])

class TestCompositor(unittest.TestCase):
    def test_valid(self):
        self.assertIn("TESTE GOAT",c.build(fixture()))
    def test_invalid(self):
        variants=[
            lambda s:s.update(finalidade="agenda_jogo_unico"),
            lambda s:s["elementos"].append(copy.deepcopy(s["elementos"][-1])),
            lambda s:s["elementos"][1].update(x=0),
            lambda s:s["elementos"][1].update(texto="X"*23),
            lambda s:s["elementos"][1].update(peso=401),
            lambda s:s["elementos"][1].update(tipo="html"),
            lambda s:s["elementos"][1].update(w=1080)]
        for change in variants:
            with self.subTest(change=change):
                s=fixture()
                change(s)
                with self.assertRaises(ValueError): c.build(s)
    def test_logo_only(self):
        import render_v2
        s=fixture()
        s["marca"]="bodinho"
        with self.assertRaisesRegex(ValueError,"logo"):
            c.build(s)
        for tipo in render_v2.LAYOUTS:
            with self.subTest(tipo=tipo):
                with self.assertRaisesRegex(ValueError,"logo"):
                    render_v2.build(dict(tipo=tipo,marca="bodinho"))
    def test_director_handoff(self):
        import json, diretor_v2
        ctx=diretor_v2.preparar({"titulo":"TESTE GOAT","ilustrativo":True},"SKILL SINTETICA PARA TESTE",[],[],{})
        spec=fixture()
        spec.update(marca="bodinho",ilustrativo=False,fonte_dado="inventada")
        result=diretor_v2.aceitar(json.dumps(spec),ctx)
        self.assertEqual(result["spec"]["marca"],"logo")
        self.assertTrue(result["spec"]["ilustrativo"])
        self.assertIsNone(result["spec"]["fonte_dado"])
        self.assertFalse(result["publicar"])
        self.assertEqual(result["status"],"revisao_pendente")
        with self.assertRaises(ValueError):
            diretor_v2.preparar({"titulo":"TESTE"},"",[],[],{})
        ctx["briefing"]["finalidade"]="agenda_jogo_unico"
        with self.assertRaises(ValueError):
            diretor_v2.aceitar(json.dumps(spec),ctx)
    def test_source(self):
        with self.assertRaises(ValueError): c.asset(dict(arquivo="../secret.png",fonte="https://example.org"))
    def test_face(self):
        s=fixture()
        s["fotos"]={"a":{}}
        s["elementos"].insert(1,dict(tipo="foto",ref="a",x=0,y=0,w=1080,h=1350,rostos_protegidos=[[100,920,100,100]]))
        with patch.object(c,"asset",return_value="dummy"),patch.object(c.r,"editorial",return_value="dummy"):
            with self.assertRaisesRegex(ValueError,"rosto"): c.build(s)
    def test_mask(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"photo.png"
            Image.new("RGB",(100,100),(20,40,60)).save(p)
            uri=c.recorte_uri(p,[[20,20],[80,20],[50,80]])
            im=Image.open(io.BytesIO(base64.b64decode(uri.split(",")[1])))
            self.assertEqual(im.getpixel((50,40)),(20,40,60,255))
            self.assertEqual(im.getpixel((0,0))[3],0)
    def test_render(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"test.png"
            c.render(fixture(),p)
            with Image.open(p) as im: self.assertEqual(im.size,(1080,1350))

if __name__=="__main__": unittest.main()
