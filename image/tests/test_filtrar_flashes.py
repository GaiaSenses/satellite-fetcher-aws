"""T22: a vetorização não pode mudar a resposta — nem count, nem eventos, nem ordem.

O laço antigo é reproduzido literalmente e comparado contra filtrar_flashes em
dados sintéticos que cobrem os cantos: fora da caixa, na borda exata (<=),
qualidade != 0, energia negativa, e um granule aleatório grande.
"""
import sys, unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from main import filtrar_flashes


def laco_antigo(lat, lon, dist, flash_lat, flash_lon, flash_energy, flash_quality):
    count = 0
    eventos = []
    latlon_diff = float(dist) / 111
    for i in range(len(flash_lat)):
        if np.abs(flash_lat[i] - lat) <= latlon_diff and np.abs(flash_lon[i] - lon) <= latlon_diff:
            if flash_quality[i] == 0:
                count += 1
                eventos.append({"latitude": float(flash_lat[i]), "longitude": float(flash_lon[i]),
                                "energy (pJ)": float(flash_energy[i] / 1e-12)})
    return count, eventos


class TestFiltrarFlashes(unittest.TestCase):
    def comparar(self, lat, lon, dist, fla, flo, fen, fq):
        antigo = laco_antigo(lat, lon, dist, fla, flo, fen, fq)
        novo = filtrar_flashes(lat, lon, dist, fla, flo, fen, fq)
        self.assertEqual(novo[0], antigo[0])
        self.assertEqual(novo[1], antigo[1])  # mesmos eventos, mesma ordem

    def test_casos_de_canto(self):
        d = 111.0  # latlon_diff = 1 grau exato
        fla = np.array([-23.0, -23.0, -24.0, -22.0, -25.5, -23.5])
        flo = np.array([-46.0, -47.0, -46.0, -45.0, -46.0, -46.5])
        fen = np.array([1e-12, 2e-12, 3e-12, 4e-12, 5e-12, -1e-12])
        fq  = np.array([0, 0, 1, 0, 0, 0])   # o 3º cai pela qualidade; o 5º pela caixa
        self.comparar(-23.0, -46.0, d, fla, flo, fen, fq)

    def test_borda_exata_inclusiva(self):
        # a 1 grau exato do centro: o <= tem que incluir
        fla = np.array([-24.0]); flo = np.array([-46.0])
        fen = np.array([1e-12]); fq = np.array([0])
        count, ev = filtrar_flashes(-23.0, -46.0, 111.0, fla, flo, fen, fq)
        self.assertEqual(count, 1)

    def test_granule_aleatorio_grande(self):
        rng = np.random.default_rng(43)
        n = 5000
        fla = rng.uniform(-60, 20, n)
        flo = rng.uniform(-90, -20, n)
        fen = rng.uniform(1e-15, 1e-10, n)
        fq  = rng.integers(0, 3, n)
        self.comparar(-12.97, -38.51, 100, fla, flo, fen, fq)

    def test_vazio(self):
        z = np.array([])
        count, ev = filtrar_flashes(0, 0, 50, z, z, z, z)
        self.assertEqual((count, ev), (0, []))


if __name__ == "__main__":
    unittest.main()
