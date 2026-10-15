"""Synthetic counting/partition regression only, not calibration evidence."""
import pytest
from review_confirmed_cohort import readiness

def rows():
    return [{'pair_id':f'new_pair{i:02d}','role':'held_out' if i==7 else 'fit',
             'original_good_top_frames':60 if i in (2,7) else 0} for i in range(2,8)]

def test_one_training_A_and_one_held_out_A_are_not_six_pairs():
    r=readiness(rows())
    assert r['training_ids_with_quality_A']==['new_pair02']
    assert r['held_out_ids_with_quality_A']==['new_pair07']
    assert r['training_ids_needing_new_quality_A']==['new_pair03','new_pair04','new_pair05','new_pair06']
    assert not r['necessary_image_quality_for_5plus1_met']

def test_even_all_image_passes_do_not_approve_calibration_or_run_fit():
    data=rows()
    for r in data:r['original_good_top_frames']=20
    result=readiness(data)
    assert result['necessary_image_quality_for_5plus1_met']
    assert not result['formal_calibration_approved'] and not result['fit_performed']

def test_nineteen_good_frames_are_not_twenty():
    data=rows();data[0]['original_good_top_frames']=19
    assert readiness(data)['training_ids_with_quality_A']==[]

@pytest.mark.parametrize('kind',['duplicate','missing','held_out_swapped'])
def test_invalid_partition_is_not_silently_repaired(kind):
    data=rows()
    if kind=='duplicate':data[-1]['pair_id']=data[0]['pair_id']
    if kind=='missing':data.pop()
    if kind=='held_out_swapped':data[-1]['role']='fit';data[0]['role']='held_out'
    with pytest.raises(ValueError):readiness(data)
