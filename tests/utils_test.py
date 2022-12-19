from vpf_730.utils import FrozenDict


def test_fdict():
    fdict = FrozenDict({'test': 123})
    assert fdict['test'] == 123
    assert 'test' in fdict
    assert list(fdict) == ['test']
    assert fdict.get('test') == 123
    assert fdict.get('nothing') is None
    assert list(fdict.values()) == [123]
    assert list(fdict.keys()) == ['test']
    assert list(fdict.items()) == [('test', 123)]
    assert repr(fdict) == "FrozenDict({'test': 123})"
