import pandas as pd

from src.features.comments import CommentsTransformer


def test_long_comments_filtered():
    transformer = CommentsTransformer()
    df = pd.DataFrame(
        {
            "latestComments": [{"text": "a" * 600}, {"text": "curto"}],
            "id": [1, 2],
        }
    )
    result = transformer.transform(df)
    assert all(result["comprimento texto"] < transformer.MAX_TEXT_LENGTH)
