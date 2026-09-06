"""Compatibility at the pymer4 0.8.x output-conversion boundary."""

from types import FunctionType

import pandas as pd


class _PymerOutputFrame(pd.DataFrame):
    """Keep pymer4's old elementwise spelling local to its converted R tables."""

    @property
    def _constructor(self):
        return _PymerOutputFrame

    def applymap(self, func, na_action=None, **kwargs):
        return self.map(func, na_action=na_action, **kwargs)


def fit_lmer(model, **kwargs):
    """Fit unchanged, adapting R output frames for pandas 3 when necessary.

    pymer4 0.8.2 calls DataFrame.applymap when formatting random-effect tables,
    after lme4 has already fit the model. pandas 3 removed that alias for map.
    Give this invocation its own R2pandas binding, whose frames retain the alias
    through query/drop operations. Neither pandas nor pymer4 module globals are
    patched, so unrelated threads and dataframe operations remain untouched.
    Model inputs, R fitting, and inference are unchanged.
    """
    fit = model.fit
    function = getattr(fit, "__func__", None)
    if hasattr(pd.DataFrame, "applymap") or function is None:
        return fit(**kwargs)
    convert = function.__globals__.get("R2pandas")
    if convert is None:
        # Newer pymer4 implementations need no legacy bridge adaptation.
        return fit(**kwargs)

    def convert_output(*args, **convert_kwargs):
        result = convert(*args, **convert_kwargs)
        return _PymerOutputFrame(result) if isinstance(result, pd.DataFrame) else result

    namespace = dict(function.__globals__, R2pandas=convert_output)
    compatible_fit = FunctionType(function.__code__, namespace, function.__name__,
                                  function.__defaults__, function.__closure__)
    compatible_fit.__kwdefaults__ = function.__kwdefaults__
    return compatible_fit(model, **kwargs)
