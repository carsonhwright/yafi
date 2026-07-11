import numpy as np
import pandas as pd
from decos import tag

@tag("outside-stdev")
def where_is_outside_stddev(df: pd.DataFrame, field):
    """Get positional indexes of df where the column that correlates to the field param
    exceeds the absolute distance from the standard deviation. The returned array can be
    used to index back into the DataFrame/Series again, e.g. df[field][result] or df.iloc[result].
    """
    if field not in df.columns:
        raise KeyError(f"field: {field} does not exist in dataframe, list of available fields is {list(df.columns)}")
    stdev = df[field].std()
    mean = df[field].mean()
    return np.where(abs(df[field] - mean) > stdev)[0]
