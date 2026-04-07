import pytest

from arm_perception import ImagePreprocessor, ColorDetector, QRCodeDetector, ContourDetector, TargetFilter, TargetFuser


@pytest.mark.parametrize('component', [ImagePreprocessor(), ColorDetector(), QRCodeDetector(), ContourDetector()])
def test_perception_components_reject_none_input(component):
    method = getattr(component, 'normalize', None) or getattr(component, 'detect')
    with pytest.raises(ValueError):
        method(None)


def test_perception_target_filter_and_fuser_validate_inputs():
    with pytest.raises(ValueError):
        TargetFilter().filter('bad')
    with pytest.raises(ValueError):
        TargetFuser().fuse('bad')
