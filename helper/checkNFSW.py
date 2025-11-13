# pip install nudenet opencv-python numpy onnxruntime
import os
import cv2
import numpy as np
from nudenet import NudeDetector
import onnxruntime as ort
from PIL import Image
import tensorflow.lite as tflite


# Option 1: NudeNet Classifier
class NudeNetChecker:
    def __init__(self):
        self.detector = NudeDetector()
        
        self.dict_thresholds = {
            "FEMALE_GENITALIA_COVERED": 0.4,
            "FACE_FEMALE": 0.9,
            "BUTTOCKS_EXPOSED": 0.3,
            "FEMALE_BREAST_EXPOSED": 0.9,
            "FEMALE_GENITALIA_EXPOSED": 0.6,
            "MALE_BREAST_EXPOSED": 0.9,
            "ANUS_EXPOSED": 0.4,
            "FEET_EXPOSED": 0.8,
            "BELLY_COVERED": 0.9,
            "FEET_COVERED": 0.9,
            "ARMPITS_COVERED": 0.9,
            "ARMPITS_EXPOSED": 0.8,
            "FACE_MALE": 0.9,
            "BELLY_EXPOSED": 0.8,
            "MALE_GENITALIA_EXPOSED": 0.4,
            "ANUS_COVERED": 0.9,
            "FEMALE_BREAST_COVERED": 0.9,
            "BUTTOCKS_COVERED": 0.5,
        }

    def detect(self, image_path):
        """
        Trả về danh sách các vùng nhạy cảm và điểm số vi phạm.
        """
        return self.detector.detect(image_path)
    
    def is_unsafe(self, image_path, threshold=0.7):
        """
        Kiểm tra xem ảnh có vùng nhạy cảm đáng kể không (ví dụ score > 0.7).
        Nếu có, return True.
        """
        detections = self.detect(image_path)
        for region in detections:
            region_class = region['class']
            region_threshold = self.dict_thresholds.get(region_class, threshold)
            region_score = region['score']
            #
            print(region_class, region_score, region_threshold)
            if region_score >= region_threshold:
                return True
        return False

# Option 2: Rule-based skin exposure checker (OpenCV)
class SkinRatioChecker:
    def __init__(self, lower_thresh=(0, 133, 77), upper_thresh=(255, 173, 127)):
        self.lower_thresh = np.array(lower_thresh, dtype="uint8")
        self.upper_thresh = np.array(upper_thresh, dtype="uint8")

    def compute_skin_ratio(self, image_path):
        image = cv2.imread(image_path)
        if image is None:
            raise ValueError("Không thể đọc ảnh: " + image_path)
        image_ycrcb = cv2.cvtColor(image, cv2.COLOR_BGR2YCrCb)
        skin_mask = cv2.inRange(image_ycrcb, self.lower_thresh, self.upper_thresh)
        skin_ratio = np.count_nonzero(skin_mask) / skin_mask.size
        return skin_ratio

# Option 3: NSFW Classifier via ONNX
class ONNXNSFWChecker:
    def __init__(self, model_path):
        if not os.path.exists(model_path):
            raise FileNotFoundError(f"Model {model_path} not found.")
        self.session = ort.InferenceSession(model_path)
        self.input_name = self.session.get_inputs()[0].name

    def preprocess(self, image_path):
        image = Image.open(image_path).convert('RGB').resize((224, 224))
        image_np = np.array(image).astype('float32') / 255.0
        image_np = image_np.transpose(2, 0, 1)  # HWC to CHW
        return np.expand_dims(image_np, axis=0)

    def predict(self, image_path):
        input_tensor = self.preprocess(image_path)
        outputs = self.session.run(None, {self.input_name: input_tensor})
        nsfw_score = float(outputs[0][0][1])  # Index 1 = 'nsfw' class
        return {'nsfw_score': nsfw_score, 'sfw_score': 1 - nsfw_score}
    
# Option 4: NSFW TFLite
class NSFWTFLiteChecker:
    def __init__(self, model_path):
        
        if not os.path.exists(model_path):
            raise FileNotFoundError(f"Model {model_path} not found.")
        self.interpreter = tflite.Interpreter(model_path=model_path)
        self.interpreter.allocate_tensors()
        self.input_details = self.interpreter.get_input_details()
        self.output_details = self.interpreter.get_output_details()
        self.input_size = (224, 224)
        self.labels = ["Drawing", "Hentai", "Neutral", "Porn", "Sexy"]
        self.dict_thresholds = {
            "Drawing": 1,
            "Hentai": 0.6,
            "Neutral": 1,
            "Porn": 0.6,
            "Sexy": 0.5,
        }

    def preprocess(self, image_path):
        image = Image.open(image_path).convert('RGB').resize(self.input_size)
        img_np = np.array(image).astype('float32') / 255.0
        img_np = np.expand_dims(img_np, axis=0)  # shape [1, 224, 224, 3]
        return img_np.astype(self.input_details[0]["dtype"])

    def predict(self, image_path):
        input_tensor = self.preprocess(image_path)
        self.interpreter.set_tensor(self.input_details[0]['index'], input_tensor)
        self.interpreter.invoke()
        output_data = self.interpreter.get_tensor(self.output_details[0]['index'])[0]
        scores = {label: round(float(score), 4) for label, score in zip(self.labels, output_data)}
        print(f"scores: {scores}")
        scores["max_class"] = max(scores, key=lambda k: scores[k])
        # nsfw_score = float(output_data[1])  # Index 1 = 'nsfw' class
        # print(f"NSFW score: {nsfw_score}, SFW score: {1 - nsfw_score}")
        return scores
    
    def predict_unsafe(self, image_path):
        scores = self.predict(image_path)
        max_class = scores["max_class"]
        max_score = scores[max_class]
        threshold = self.dict_thresholds.get(max_class, 0.7)
        return max_score >= threshold


def test_nsfw(image_path):
    # NudeNet
    nude_checker = NudeNetChecker()
    print("NudeNet:", nude_checker.is_unsafe(image_path))

    # Skin Exposure
    skin_checker = SkinRatioChecker()
    print("Skin ratio:", skin_checker.compute_skin_ratio(image_path))

    # # ONNX NSFW Classifier (bạn cần tải mô hình từ repo như OpenNSFW)
    # onnx_checker = ONNXNSFWChecker("open_nsfw_model.onnx")
    # print("ONNX NSFW:", onnx_checker.predict(image_path))

    # TFLite NSFW Classifier (bạn cần tải mô hình từ repo như NSFW TFLite)
    tflite_checker = NSFWTFLiteChecker("saved_model.tflite")
    print("TFLite NSFW:", tflite_checker.predict(image_path))

def NSFW_check_image(image_path):
    nude_checker = NudeNetChecker()
    nudedet_is_unsafe = nude_checker.is_unsafe(image_path)
    print("NudeNet unsafe:", nudedet_is_unsafe)

    # Skin Exposure
    skin_checker = SkinRatioChecker()
    skin_ratio = skin_checker.compute_skin_ratio(image_path)
    print("Skin ratio:", skin_ratio)

    skin_is_unsafe = skin_ratio >= 0.5  # Ngưỡng tùy chỉnh

    # TFLite NSFW Classifier (bạn cần tải mô hình từ repo như NSFW TFLite)
    tflite_checker = NSFWTFLiteChecker("saved_model.tflite")
    nsfw_tflite_is_unsafe = tflite_checker.predict_unsafe(image_path)

    is_unsafe = nudedet_is_unsafe or skin_is_unsafe or nsfw_tflite_is_unsafe

    return is_unsafe

def run_command_line():
    '''
    Input folder of images, check NSFW for each image, print results.
    from results create unsafe_ig folder and move unsafe images there.
    input folder path is entered from command line
    '''
    import shutil
    from tqdm import tqdm
    folder = input("Thư mục chứa ảnh: ").strip()
    if not os.path.exists(folder):
        print("Thư mục không tồn tại.")
        return
    unsafe_folder = os.path.join(folder, "unsafe_ig")
    os.makedirs(unsafe_folder, exist_ok=True)

    img_extensions = {".jpg", ".jpeg", ".png", ".bmp", ".gif"}
    img_files = [os.path.join(folder, f) for f in os.listdir(folder) if os.path.splitext(f.lower())[1] in img_extensions]
    if not img_files:
        print("Không tìm thấy ảnh hợp lệ trong thư mục.")
        return
    for img_path in tqdm(img_files, desc="Kiểm tra ảnh NSFW", unit="ảnh"):
        try:
            is_unsafe = NSFW_check_image(img_path)
            if is_unsafe:
                print(f"Ảnh NSFW: {img_path}")
                shutil.move(img_path, os.path.join(unsafe_folder, os.path.basename(img_path)))
            else:
                print(f"Ảnh SFW: {img_path}")
        except Exception as e:
            print(f"Lỗi khi xử lý ảnh {img_path}: {e}")




if __name__ == "__main__":
    # test_image_path = r"F:\pic\2025-05-12\00420-20250512_162138_100239_4073398145.png"  # Thay bằng đường dẫn ảnh của bạn
    # test_nsfw(test_image_path)
    run_command_line()