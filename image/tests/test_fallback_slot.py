"""T23: slot GOES ainda não publicado recua para o anterior em vez de dar 501."""
import sys, unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import aws_access
from aws_access import awsAccessGOES


class FakeS3:
    def __init__(self, vazios_antes_do_cheio):
        self.vazios = vazios_antes_do_cheio
        self.prefixos = []
        self.baixados = []

    def list_objects_v2(self, Bucket, Prefix, Delimiter):
        self.prefixos.append(Prefix)
        if len(self.prefixos) <= self.vazios:
            return {}
        return {"Contents": [{"Key": f"{Prefix}granulo_teste.nc"}]}

    def download_file(self, bucket, object_key, path):
        self.baixados.append(object_key)
        Path(path).write_text("granulo de teste")


class TestFallbackSlot(unittest.TestCase):
    def _rodar(self, vazios):
        fake = FakeS3(vazios)
        with patch.object(aws_access.boto3, "client", return_value=fake):
            caminho = awsAccessGOES.download_aws("2")
        return fake, caminho

    def test_slot_atual_existente_nao_recua(self):
        fake, caminho = self._rodar(vazios=0)
        self.assertEqual(len(fake.prefixos), 1)
        self.assertTrue(Path(caminho).exists())

    def test_slot_vazio_recua_para_o_anterior(self):
        fake, caminho = self._rodar(vazios=1)
        self.assertEqual(len(fake.prefixos), 2)
        self.assertNotEqual(fake.prefixos[0], fake.prefixos[1])
        self.assertTrue(Path(caminho).exists())

    def test_tres_vazios_ainda_encontra_no_quarto(self):
        fake, caminho = self._rodar(vazios=3)
        self.assertEqual(len(fake.prefixos), 4)
        self.assertTrue(Path(caminho).exists())

    def test_tudo_vazio_levanta_erro_com_os_prefixos(self):
        fake = FakeS3(99)
        with patch.object(aws_access.boto3, "client", return_value=fake):
            with self.assertRaises(FileNotFoundError) as ctx:
                awsAccessGOES.download_aws("2")
        self.assertEqual(len(fake.prefixos), 4)
        self.assertIn("4 prefixes", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
