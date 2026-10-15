"""Offline-only tests; no ROS/CAN/device imports at module level."""
import ast
from pathlib import Path
from types import SimpleNamespace
import sys
import pytest

sys.path.insert(0,str(Path(__file__).parent))
import collect_depth_controls as controls


@pytest.mark.parametrize('data,success', [(0,True),(0,False),(100,True),(-1,False)])
def test_raw_reply_never_becomes_verified_physical_value(data,success):
    response=SimpleNamespace(data=data,success=success,message='unchanged raw text')
    row=controls.response_record(controls.SERVICES[0],response,1.,2.)
    assert row['raw_response']==dict(data=data,success=success,message='unchanged raw text')
    assert row['physical_value'] is None and row['physical_units'] is None
    assert not row['hardware_property_status_verified']


def test_timeout_has_no_fake_zero():
    row=controls.response_record(controls.SERVICES[1],None,1.,2.,'response_timeout')
    assert row['raw_response'] is None and row['error']=='response_timeout'


@pytest.mark.parametrize('seconds',[0,31,float('nan'),float('inf')])
def test_bad_bounds_rejected_before_ros(tmp_path,seconds):
    with pytest.raises(ValueError):
        controls.collect(tmp_path/'new.json',seconds)


def test_no_overwrite_even_if_ros_missing(tmp_path):
    output=tmp_path/'existing.json';output.write_text('original')
    with pytest.raises(FileExistsError):
        controls.collect(output,20)
    assert output.read_text()=='original'


def test_cannot_select_setter_or_arm_service():
    for name in ['/camera/set_depth_exposure','/enable_srv','/camera/set_laser_enable']:
        with pytest.raises(ValueError):
            controls.response_record(name,None,None,1.)


def test_no_publishers_processes_or_configurable_service_names():
    tree=ast.parse(Path(controls.__file__).read_text())
    attrs={n.attr for n in ast.walk(tree) if isinstance(n,ast.Attribute)}
    assert not attrs & {'create_publisher','Popen','run','system','publish'}
    assert controls.SERVICES==('/camera/get_depth_exposure','/camera/get_depth_gain')


def test_existing_native_output_rejected_before_ros(tmp_path):
    native=tmp_path/'existing';native.mkdir()
    with pytest.raises(FileExistsError):
        controls.collect(tmp_path/'new.json',20,native)
