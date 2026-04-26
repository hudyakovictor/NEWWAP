import json
import os
import sys
from pathlib import Path

import cv2
import numpy as np
import torch
from torchvision import transforms

# Path to the head-pose-estimation library
HPE_PATH = "/Users/victorkhudyakov/dutin/core/head-pose-estimation"
sys.path.insert(0, HPE_PATH)

# We need to be in the library directory to load models correctly
original_cwd = os.getcwd()
os.chdir(HPE_PATH)

try:
    from models import SCRFD, get_model
    from utils.general import compute_euler_angles_from_rotation_matrices
finally:
    os.chdir(original_cwd)

# Ленивый singleton 3DDFA (тяжёлый) — только если head-pose не классифицировал ракурс
# Упрощенная реализация без сложного pipeline reconstruction
_ddfa_initialized = False


def _canonical_yaw_deg(raw_yaw_deg: float, *, sign_env_key: str = "DUTIN_POSE_YAW_SIGN", default_sign: str = "-1") -> float:
    """
    Сырое значение yaw из матрицы поворота (см. compute_euler_angles в head-pose-estimation):
    ось и знак совпадают с обучением на 300W-LP / AFLW2000.

    Пороги в pose_settings.json заданы так, что «левый/правый профиль» = какая щека
    обращена к камере (анатомически). У модели знак часто обратен этой интерпретации.

    Для 3DDFA используй DUTIN_DDFA_YAW_SIGN (по умолчанию 1 — без доп. инверсии относительно BFM).
    """
    sign = float(os.environ.get(sign_env_key, default_sign))
    return sign * raw_yaw_deg


def _pose_from_3ddfa(image_path: Path, pose_detector: "PoseDetector") -> dict | None:
    """
    Возвращает pose dict как у get_pose, с полями pose_source, или None если лицо/модель не сработали.
    angles_deg из реконструкции: [pitch, yaw, roll] (см. pipeline/core.py).
    Использует упрощенный подход из runner_3ddfa_v3.py для большей надежности.
    """
    try:
        import os
        import sys

        import numpy as np
        import torch
        from PIL import Image

        # Настройка путей к 3DDFA_v3
        ddfa_root = "/Users/victorkhudyakov/dutin/core/3ddfa_v3"
        if ddfa_root not in sys.path:
            sys.path.insert(0, ddfa_root)

        original_cwd = os.getcwd()
        os.chdir(ddfa_root)

        try:
            from face_box import face_box
            from model.recon import face_model

            # Создаем аргументы для модели (минимальная конфигурация для углов)
            class Args:
                device = 'cpu'
                detector_device = 'cpu'
                iscrop = True
                detector = 'retinaface'
                backbone = 'resnet50'

            args = Args()

            # Инициализируем модели (ленивая инициализация)
            if not hasattr(_pose_from_3ddfa, '_ddfa_model'):
                _pose_from_3ddfa._ddfa_model = face_model(args)
                _pose_from_3ddfa._ddfa_detector = face_box(args).detector
                print("[detect_pose] 3DDFA_v3 model initialized", flush=True)

            recon_model = _pose_from_3ddfa._ddfa_model
            facebox_detector = _pose_from_3ddfa._ddfa_detector

            # Загружаем и обрабатываем изображение
            im = Image.open(image_path).convert('RGB')

            # PREVENT HANG: RetinaFace on CPU freezes if resolution is 4K. Hard cap at 1024.
            im.thumbnail((1024, 1024))

            # Детекция лица
            trans_params, im_tensor = facebox_detector(im)
            if im_tensor is None:
                print(f"[detect_pose] 3DDFA: No face detected in {image_path.name}", flush=True)
                return None

            # Реконструкция для получения углов
            recon_model.input_img = im_tensor.to(args.device)
            with torch.no_grad():
                alpha = recon_model.net_recon(recon_model.input_img)
                alpha_dict = recon_model.split_alpha(alpha)
                angles = alpha_dict['angle'].detach().cpu().numpy()[0]
                pitch, yaw, roll = angles[0], angles[1], angles[2]

                pitch_deg = float(pitch * 180 / np.pi)
                yaw_deg = float(yaw * 180 / np.pi)
                roll_deg = float(roll * 180 / np.pi)

            # Применяем каноническую нормализацию yaw
            canonical_yaw = _canonical_yaw_deg(yaw_deg, sign_env_key="DUTIN_DDFA_YAW_SIGN", default_sign="1")
            bucket = pose_detector.get_bucket_name(canonical_yaw)

            print(f"[detect_pose] 3DDFA success: {image_path.name} -> yaw={canonical_yaw:.1f}, pitch={pitch_deg:.1f}, roll={roll_deg:.1f}", flush=True)

            return {
                "yaw": canonical_yaw,
                "pitch": pitch_deg,
                "roll": roll_deg,
                "bucket": bucket,
                "pose_source": "3ddfa_v3",
                "raw_yaw_3ddfa_deg": yaw_deg,
                "fallback_used": True,
            }

        finally:
            os.chdir(original_cwd)

    except Exception as e:
        print(f"[detect_pose] 3DDFA fallback error: {e}", flush=True)
        import traceback
        traceback.print_exc()
        return None


class PoseDetector:
    def __init__(self, device=None):
        if device is None:
            self.device = torch.device('mps' if torch.backends.mps.is_available() else 'cpu')
        else:
            self.device = torch.device(device)

        # Initialize face detector
        self.face_detector = SCRFD(model_path=os.path.join(HPE_PATH, "weights/det_10g.onnx"))

        # Initialize head pose model
        self.head_pose = get_model('mobilenetv3_large', num_classes=6, pretrained=False)
        state_dict = torch.load(os.path.join(HPE_PATH, "weights/mobilenetv3_large.pt"), map_location=self.device, weights_only=False)
        self.head_pose.load_state_dict(state_dict)
        self.head_pose.to(self.device)
        self.head_pose.eval()

        self.settings_path = os.path.join(os.path.dirname(__file__), "pose_settings.json")
        self.load_settings()

    def load_settings(self):
        try:
            if os.path.exists(self.settings_path):
                with open(self.settings_path, 'r') as f:
                    self.settings = json.load(f)
            else:
                raise FileNotFoundError()
        except Exception as e:
            print(f"Error loading pose settings: {e}")
            # Fallback defaults
            self.settings = {
                "frontal": {"min": -10, "max": 10},
                "left_profile": {"min": -180, "max": -70},
                "left_threequarter_deep": {"min": -70, "max": -45},
                "left_threequarter_mid": {"min": -45, "max": -25},
                "left_threequarter_light": {"min": -25, "max": -10},
                "right_profile": {"min": 70, "max": 180},
                "right_threequarter_deep": {"min": 45, "max": 70},
                "right_threequarter_mid": {"min": 25, "max": 45},
                "right_threequarter_light": {"min": 10, "max": 25}
            }

    def get_bucket_name(self, yaw_deg):
        # Find which range the yaw belongs to
        for bucket, range_info in self.settings.items():
            if range_info["min"] <= yaw_deg <= range_info["max"]:
                return bucket
        return "unclassified"

    def pre_process(self, image):
        image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        transform = transforms.Compose([
            transforms.ToPILImage(),
            transforms.Resize(224),
            transforms.ToTensor(),
            transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
        ])
        image = transform(image)
        image_batch = image.unsqueeze(0)
        return image_batch

    def expand_bbox(self, x_min, y_min, x_max, y_max, factor=0.2):
        width = x_max - x_min
        height = y_max - y_min
        x_min_new = x_min - int(factor * height)
        y_min_new = y_min - int(factor * width)
        x_max_new = x_max + int(factor * height)
        y_max_new = y_max + int(factor * height)
        return max(0, x_min_new), max(0, y_min_new), x_max_new, y_max_new

    def _pose_from_head_estimation(self, frame: np.ndarray) -> dict:
        """Только head-pose-estimation; без fallback. bucket может быть unclassified."""
        with torch.no_grad():
            bboxes, _ = self.face_detector.detect(frame)
            if len(bboxes) == 0:
                return {"yaw": 0.0, "pitch": 0.0, "roll": 0.0, "bucket": "unclassified", "pose_source": "head_pose", "hpe_face_found": False}

            bbox = bboxes[0]
            x_min, y_min, x_max, y_max = map(int, bbox[:4])
            x_min, y_min, x_max, y_max = self.expand_bbox(x_min, y_min, x_max, y_max)

            h, w = frame.shape[:2]
            x_min, y_min = max(0, x_min), max(0, y_min)
            x_max, y_max = min(w, x_max), min(h, y_max)

            image = frame[y_min:y_max, x_min:x_max]
            if image.size == 0:
                return {"yaw": 0.0, "pitch": 0.0, "roll": 0.0, "bucket": "unclassified", "pose_source": "head_pose", "hpe_face_found": False}

            image = self.pre_process(image)
            image = image.to(self.device)

            rotation_matrix = self.head_pose(image)
            euler = np.degrees(compute_euler_angles_from_rotation_matrices(rotation_matrix))

            p_pred_deg = float(euler[:, 0].cpu().numpy()[0])
            raw_yaw = float(euler[:, 1].cpu().numpy()[0])
            r_pred_deg = float(euler[:, 2].cpu().numpy()[0])
            y_pred_deg = _canonical_yaw_deg(raw_yaw, sign_env_key="DUTIN_POSE_YAW_SIGN", default_sign="1")

            bucket = self.get_bucket_name(y_pred_deg)

            return {
                "yaw": y_pred_deg,
                "pitch": p_pred_deg,
                "roll": r_pred_deg,
                "bucket": bucket,
                "pose_source": "head_pose",
                "hpe_face_found": True,
                "raw_yaw_hpe_deg": raw_yaw,
            }

    def get_pose(self, image_path: str | Path) -> dict:
        p = Path(image_path)
        frame = cv2.imread(str(p))
        if frame is None:
            return {
                "yaw": 0, "pitch": 0, "roll": 0, "bucket": "unclassified",
                "pose_source": "none", "hpe_bucket": "unclassified", "needs_manual_review": True,
                "fallback_attempted": False, "fallback_used": False, "hpe_face_found": False,
            }

        try:
            hpe = self._pose_from_head_estimation(frame)
        except Exception as e:
            print(f"Pose detection internal error (HPE): {e}", flush=True)
            hpe = {"yaw": 0.0, "pitch": 0.0, "roll": 0.0, "bucket": "unclassified", "pose_source": "head_pose", "hpe_face_found": False}

        hpe_bucket = hpe.get("bucket", "unclassified")

        if hpe_bucket != "unclassified":
            out = {
                **hpe,
                "hpe_bucket": hpe_bucket,
                "needs_manual_review": False,
                "fallback_attempted": False,
                "fallback_used": False,
            }
            # убираем служебные ключи из лишнего
            return out

        # Fallback: 3DDFA-V3 (та же сетка, что и в pipeline/reconstruction)
        ddfa = _pose_from_3ddfa(p, self)
        if ddfa is not None:
            return {
                **ddfa,
                "hpe_bucket": "unclassified",
                "needs_manual_review": True,
                "hpe_fallback_reason": "head_pose_unclassified",
                "fallback_attempted": True,
                "hpe_face_found": bool(hpe.get("hpe_face_found")),
            }

        out = {
            "yaw": float(hpe.get("yaw", 0)),
            "pitch": float(hpe.get("pitch", 0)),
            "roll": float(hpe.get("roll", 0)),
            "bucket": "unclassified",
            "pose_source": "none",
            "hpe_bucket": "unclassified",
            "needs_manual_review": True,
            "hpe_fallback_reason": "3ddfa_failed",
            "fallback_attempted": True,
            "fallback_used": False,
            "hpe_face_found": bool(hpe.get("hpe_face_found")),
        }
        return out

    def get_bucket(self, image_path: str | Path) -> str:
        return self.get_pose(image_path)["bucket"]

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python detect_pose.py <image_path>")
        sys.exit(1)

    img_path = Path(sys.argv[1])
    if not img_path.exists():
        print("unclassified")
        sys.exit(0)

    detector = PoseDetector()
    print(detector.get_bucket(img_path))
