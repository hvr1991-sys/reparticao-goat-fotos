"""Rodada visual local/CI, com fotos já rastreadas e dados explicitamente ilustrativos.

Não usa APIs de IA, não acessa Supabase, não aprova nem publica nenhuma peça.
Uso: python -m kit.verify_renderer /tmp/goat-render-review
"""
from pathlib import Path
import hashlib
import json
import sys

from kit.render import SKILL, render

ROOT = Path(__file__).resolve().parent.parent


def main(destination):
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((SKILL / "manifest.json").read_text())
    for item in manifest["files"]:
        path = SKILL / item["path"]
        if hashlib.sha256(path.read_bytes()).hexdigest() != item["sha256"]:
            raise RuntimeError(f"Arquivo original alterado: {item['path']}")

    paths = [
        "fotos/010777c4-1957-45ec-95a5-f3c375c227ac-j58/1.png",
        "fotos/01737ba0-b68b-415a-b542-779f132a0f88-j51/1.png",
        "fotos/050803b6-dd08-4e29-8d82-a05cd70b4829-j95/1.png",
        "fotos/399ca7c2-a821-42d7-8509-02ed455f5125-j112/1.jpg",
    ]
    photos = [str(ROOT / path) for path in paths]
    provenance = []
    for path in paths:
        local = ROOT / path
        meta = json.loads((local.parent / "meta.json").read_text())
        item = next(f for f in meta["fotos"] if f.get("arquivo") == local.name and f.get("ok") is True)
        provenance.append({"path": path, "pagina": item["pagina"], "credito": item["credito"],
                           "sha256": hashlib.sha256(local.read_bytes()).hexdigest()})
    base = {"ilustrativo": True, "marca": "logo", "data_dia_semana": "SÁBADO", "data_resto": "28 DE NOVEMBRO"}
    games = [{"horario": time, "rotulo": "CAMPEONATO DE EXEMPLO", "confronto": teams, "foto": photo, "foco": focus}
             for time, teams, photo, focus in zip(
                 ["16H30", "18H30", "20H", "22H"],
                 ["TIME A X TIME B", "TIME C X TIME D", "TIME E X TIME F", "TIME G X TIME H"],
                 photos, ["70% 25%", "70% 15%", "50% 28%", "65% 20%"])]
    specs = {
        "agenda-fiel": {**base, "tipo": "agenda", "jogos": games},
        "jogo-unico": {**base, "tipo": "jogo_unico", "foto": photos[3], "foco": "38% 30%",
                       "campeonato": "CAMPEONATO DE EXEMPLO", "horario": "22H", "confronto": "TIME A X TIME B"},
        "post-lateral": {**base, "tipo": "manchete", "foto": photos[0], "foco": "80% 30%",
                         "titulo": [{"texto": "SUA PAIXÃO"}, {"texto": "PELO JOGO", "amarelo": True}],
                         "apoio": "PRÉVIA DE COMPOSIÇÃO", "alinhamento": "esquerda",
                         "layout": {"x": 60, "y": 930, "largura": 800}},
        "tarja-video": {**base, "tipo": "tarja_video", "foto": photos[3], "foco": "38% 25%",
                        "texto": ["TEXTO DE EXEMPLO", "PARA A TARJA"]},
    }
    report = {"source_files_verified": len(manifest["files"]), "previews": {}, "provenance": provenance,
              "scope": "Renderização real e conferência geométrica. Não constitui aprovação editorial ou homologação das IAs."}
    for name, spec in specs.items():
        result = render(spec, destination / f"{name}.png")
        if name == "agenda-fiel" and any(c["width"] != 910 or c["height"] != 111 for c in result["cards"]):
            raise RuntimeError("As medidas dos cards não correspondem à skill original.")
        report["previews"][name] = result
        # Paths relativos, para que os exemplos possam ser reproduzidos em outra máquina.
        serialized = json.dumps(spec, ensure_ascii=False, indent=2).replace(str(ROOT) + "/", "")
        (destination / f"{name}.json").write_text(serialized + "\n")
    (destination / "render-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"previews": list(report["previews"]), "source_files_verified": report["source_files_verified"]}))
    return report


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "/tmp/goat-render-review")
