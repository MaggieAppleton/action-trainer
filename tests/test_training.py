import importlib.util
import tempfile
import unittest
from pathlib import Path

from sklearn.tree import DecisionTreeClassifier

from features import FEATURE_NAMES, extract_features
from train import train, write_model


class FeatureTests(unittest.TestCase):
    def test_resting_window_has_expected_gravity_and_low_variance(self):
        rows = [(0, 0, 16384, 3, 0, 0)] * 20
        values = extract_features(rows)
        self.assertEqual(len(values), len(FEATURE_NAMES))
        self.assertAlmostEqual(values[0], 1.0)
        self.assertAlmostEqual(values[1], 0.0)
        self.assertAlmostEqual(values[2], 1.0)
        self.assertAlmostEqual(values[3], 1.0)

    def test_empty_window_is_rejected(self):
        with self.assertRaises(ValueError):
            extract_features([])


class TrainingTests(unittest.TestCase):
    def test_generated_model_defaults_unknown_and_empty_windows_to_still(self):
        model = DecisionTreeClassifier(random_state=0)
        model.fit([[0.0] * len(FEATURE_NAMES), [1.0] * len(FEATURE_NAMES)], ["unknown", "walk"])
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "model.py"
            write_model(model, path)
            spec = importlib.util.spec_from_file_location("generated_model", path)
            generated = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(generated)
            self.assertEqual(generated.predict_window([]), "still")
            self.assertEqual(generated.predict_features([0.0] * len(FEATURE_NAMES)), "still")
            self.assertEqual(generated.predict_features([1.0] * len(FEATURE_NAMES)), "walk")

    def test_training_exports_self_contained_model_and_validation_report(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            data = root / "data"
            output = root / "dist" / "model.py"
            # Two separate sessions per class make grouped validation eligible.
            for label_index, label in enumerate(("still", "walk")):
                folder = data / label
                folder.mkdir(parents=True)
                for session in range(2):
                    path = folder / f"session-{session}.csv"
                    with path.open("w", encoding="utf-8") as stream:
                        stream.write("t_ms,ax,ay,az,gx,gy,gz,events,state\n")
                        for t_ms in range(0, 2500, 20):
                            # The changing X-axis signal separates the classes.
                            ax = 0 if label_index == 0 else ((t_ms // 100) % 2) * 8000
                            stream.write(f"{t_ms},{ax},0,16384,0,0,0,0,0\n")
            report = train(data, output)
            self.assertTrue(output.is_file())
            self.assertTrue(output.with_name("report.json").is_file())
            self.assertEqual(report["grouped_validation"]["status"], "available")
            self.assertEqual(report["default_action"], "still")


if __name__ == "__main__":
    unittest.main()
