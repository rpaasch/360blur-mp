# 360blur Project Guidelines

## Setup & Commands
- **Install dependencies**: `pip install -r requirements.txt`
- **Install YOLO (optional)**: `pip install ultralytics` (for better license plate detection)
- **Download DNN models**: `python download_models.py`
- **Run application**: `python blur360_webapp.py`
- **Run test script**: `python test_blur.py` (tests blurring on a video in uploads/)
- **Lint code**: `flake8 *.py --max-line-length=100`
- **Format code**: `black *.py --line-length=88`
- **Type check**: `mypy --ignore-missing-imports *.py`
- **Translation extraction**: `pybabel extract -F babel.cfg -o messages.pot .`
- **Add language**: `pybabel init -i messages.pot -d translations -l <lang_code>`
- **Update translations**: `pybabel update -i messages.pot -d translations`
- **Compile translations**: `pybabel compile -d translations`

## Code Style
- **Imports**: Group in order: standard library → third-party → local app imports
- **Formatting**: 4-space indentation, max 88 character line length
- **Types**: Use type hints for function parameters and return values
- **Naming**: `snake_case` for variables/functions, `UPPER_CASE` for constants
- **Documentation**: Triple-quoted docstrings for modules, classes, and functions
- **Error Handling**: Use try-except with specific exceptions, provide context in error messages
- **Logging**: Use logging module with appropriate levels (info, warning, error)
- **UI Components**: Use Bootstrap classes for consistent styling

## Project Architecture
- **Web Application**: Flask app with Socket.IO for real-time progress updates
- **Video Processing**: OpenCV-based face/plate detection with DNN models
- **Internationalization**: Flask-Babel for multilingual support (da, en, de, es, it, bg)
- **File Structure**: Keep processing logic separate from web routing
- **Models Directory**: Store DNN models in `models/` folder
- **Temporary Files**: Store uploads in `uploads/`, processed files in `processed/`
- **Job Management**: Track processing status with unique job identifiers (UUIDs)