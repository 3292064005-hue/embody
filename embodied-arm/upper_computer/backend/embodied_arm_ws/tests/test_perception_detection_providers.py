from arm_perception.color_detector import ColorDetector
from arm_perception.qrcode_detector import QRCodeDetector
from arm_perception.contour_detector import ContourDetector


def test_live_external_detections_route_through_external_provider() -> None:
    frame = {
        'payload': {
            'sourceClass': 'live',
            'detectionSourceMode': 'external_detections',
            'authoritativeTargetSource': 'real_detector',
            'cameraLive': True,
            'frameIngressLive': True,
            'detections': [
                {'id': 'live_red_01', 'detector': 'color', 'label': 'red', 'x': 0.12, 'y': 0.03, 'yaw': 0.0, 'confidence': 0.91},
                {'id': 'live_qr_01', 'detector': 'qr', 'label': 'marker', 'qr_text': 'BIN_A', 'x': 0.18, 'y': 0.01, 'yaw': 0.0, 'confidence': 0.95},
                {'id': 'live_shape_01', 'detector': 'shape', 'label': 'block', 'x': 0.15, 'y': -0.02, 'yaw': 0.2, 'confidence': 0.88},
            ],
        }
    }

    color = ColorDetector().detect(frame)
    qr = QRCodeDetector().detect(frame)
    contour = ContourDetector().detect(frame)

    assert color and color[0]['target_id'] == 'live_red_01'
    assert color[0]['detection_provider'] == 'external_detections'
    assert qr and qr[0]['qr_text'] == 'BIN_A'
    assert contour and contour[0]['target_id'] == 'live_shape_01'


def test_live_frame_without_authoritative_detections_stays_fail_closed() -> None:
    frame = {
        'payload': {
            'sourceClass': 'live',
            'detectionSourceMode': 'real_image_required',
            'authoritativeTargetSource': 'real_image_required',
            'cameraLive': True,
            'frameIngressLive': True,
            'targets': [{'id': 'should_not_leak', 'detector': 'color', 'label': 'red', 'confidence': 0.9}],
        }
    }
    assert ColorDetector().detect(frame) == []
