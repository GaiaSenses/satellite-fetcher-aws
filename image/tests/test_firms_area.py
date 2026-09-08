"""Regressão do BUG-03: a caixa enviada à FIRMS não pode mudar com o conserto.

O código antigo invertia o Point (lat, lon) e compensava invertendo a ordem dos
bounds na URL. A correção troca os dois ao mesmo tempo — e este teste prova, com
a fórmula antiga reproduzida literalmente, que a string final é idêntica. Se um
dia alguém "consertar" só metade, a saída muda e isto fica vermelho.
"""
import sys, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from shapely.geometry import Point
from main import firms_area


def formula_antiga(lat, lon, dist):
    # Reprodução literal do código pré-correção (Point invertido + ordem trocada).
    point = Point(float(lat), float(lon))
    buffer = point.buffer(float(dist) / 111)
    minx, miny, maxx, maxy = buffer.bounds
    return f"{miny},{minx},{maxy},{maxx}"


CASOS = [
    # a coordenada de referência que sempre viveu no comentário do handler
    ("-22.851692221661406", "47.1276886499418", "100"),
    ("-23.5528381", "-46.6621533", "100"),   # São Paulo, oeste negativo
    ("45.0", "7.6", "50"),                   # hemisfério norte
    ("0", "0", "10"),                        # origem, dist default do /fire
    (-12.97, -38.50, 50),                    # números, não strings
]


class TestFirmsArea(unittest.TestCase):
    def test_identica_a_formula_antiga(self):
        for lat, lon, dist in CASOS:
            with self.subTest(lat=lat, lon=lon, dist=dist):
                self.assertEqual(firms_area(lat, lon, dist),
                                 formula_antiga(lat, lon, dist))

    def test_ordem_geografica_correta(self):
        # west,south,east,north — e o centro da caixa é o ponto pedido
        west, south, east, north = map(float, firms_area(-22.85, 47.13, 100).split(","))
        self.assertLess(west, east)
        self.assertLess(south, north)
        self.assertAlmostEqual((west + east) / 2, 47.13, places=6)
        self.assertAlmostEqual((south + north) / 2, -22.85, places=6)


if __name__ == "__main__":
    unittest.main()
