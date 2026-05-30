# src/schemas.py

PROFILES_DTYPE: dict = {
    "inputUrl": "str",
    "id": "str",
    "username": "str",
    "followersCount": "int32",
    "followsCount": "int32",
    "hasChannel": "bool",
    "isBusinessAccount": "bool",
    "joinedRecently": "bool",
    "businessCategoryName": "category",
    "private": "bool",
    "verified": "bool",
    "igtvVideoCount": "int32",
    "postsCount": "int32",
}

REELS_DTYPE: dict = {
    "inputUrl": "object",
    "id": "str",
    "type": "object",
    "commentsCount": "int64",
    "likesCount": "int64",
    "videoViewCount": "int64",
    "videoPlayCount": "int64",
    "alt": "float64",
    "videoDuration": "float64",
    "isSponsored": "bool",
    "isCommentsDisabled": "bool",
    "isPinned": "float64",
    "data_hora": "datetime64[ns]",
    "Tipo": "object",
}
