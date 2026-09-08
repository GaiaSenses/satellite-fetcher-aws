"""T20: entrada inválida responde 400 — nunca 502 — e dist tem um contrato só.

O handler é chamado direto, com as funções de dados substituídas por dublês:
o que se testa aqui é o contrato de borda, não a rede.
"""
import json, sys, unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import main


def evento(path, **params):
    return {"path": path, "queryStringParameters": {k: str(v) for k, v in params.items()}}


class TestValidacao(unittest.TestCase):
    def status(self, resp):
        return resp["statusCode"]

    def test_lat_nao_numerico_da_400(self):
        for rota in ("/fire", "/lightning", "/rain"):
            with self.subTest(rota=rota):
                r = main.handler(evento(rota, lat="abc", lon="-46.6"), {})
                self.assertEqual(self.status(r), 400)

    def test_fora_de_faixa_da_400(self):
        self.assertEqual(self.status(main.handler(evento("/fire", lat=91, lon=0), {})), 400)
        self.assertEqual(self.status(main.handler(evento("/fire", lat=0, lon=181), {})), 400)

    def test_dist_absurdo_ou_invalido_da_400(self):
        self.assertEqual(self.status(main.handler(evento("/fire", lat=-23, lon=-46, dist=100000), {})), 400)
        self.assertEqual(self.status(main.handler(evento("/lightning", lat=-23, lon=-46, dist="muito"), {})), 400)
        self.assertEqual(self.status(main.handler(evento("/fire", lat=-23, lon=-46, dist=0), {})), 400)

    def test_faltando_continua_400(self):
        self.assertEqual(self.status(main.handler(evento("/fire", lat=-23), {})), 400)

    def test_valido_passa_com_default_unico(self):
        recebidos = {}
        def dubles(lat, lon, dist):
            recebidos["args"] = (lat, lon, dist)
            return {"count": 0, "events": []}
        with patch.object(main, "get_fire_data", dubles):
            r = main.handler(evento("/fire", lat=-23.55, lon=-46.66), {})
        self.assertEqual(self.status(r), 200)
        self.assertEqual(recebidos["args"], (-23.55, -46.66, main.DIST_PADRAO))
        self.assertEqual(main.DIST_PADRAO, 50)

    def test_rain_ignora_dist_invalido_nao_mas_valida_coordenada(self):
        def duble(lat, lon):
            return {"count": 0}
        with patch.object(main, "get_rain_data", duble):
            r = main.handler(evento("/rain", lat=-23.55, lon=-46.66), {})
        self.assertEqual(self.status(r), 200)


if __name__ == "__main__":
    unittest.main()
