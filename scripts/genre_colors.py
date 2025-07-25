# genre_colors.py

GENRE_COLOR_MAP = {
    "Movie": "#E53935",
    "Drama": "#8E24AA",
    "Comedy": "#FDD835",
    "Action": "#FB8C00",
    "Documentary": "#43A047",
    "News": "#1E88E5",
    "Sports": "#00ACC1",
    "Kids": "#D81B60",
    "Talk Show": "#6D4C41",
    "Music": "#3949AB",
    "Reality": "#5E35B1",
    "Cooking": "#7CB342",
    "Travel": "#00897B",
    "Game Show": "#F4511E",
    "Horror": "#D32F2F",
    "Sci-Fi": "#7E57C2",
    "Fantasy": "#AB47BC",
    "Mystery": "#8D6E63",
    "Western": "#A1887F",
    "History": "#C0CA33",
    "Romance": "#EC407A",
    "Animation": "#FF7043",
    "Crime": "#6D4C41",
    "Adventure": "#26A69A",
    "War": "#B71C1C",
    "Thriller": "#455A64",
    "Other": "#9E9E9E"
}

def get_color_for_genre(genre_name: str) -> str:
    genre_name = genre_name.strip().lower()
    for key, color in GENRE_COLOR_MAP.items():
        if key.lower() in genre_name:
            return color
    return GENRE_COLOR_MAP["Other"]
