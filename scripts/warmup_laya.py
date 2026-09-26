from app.config import get_settings
from app.services.classifiers import LayaClassifier


settings = get_settings()
classifier = LayaClassifier(settings.laya_model, settings.laya_device, settings.laya_max_loaded)
result = classifier.classify(
    "Interview invitation for Software Engineer Intern",
    "recruiting@example.com",
    "We would like to schedule an interview for your application next Tuesday.",
)
print(result.model_dump_json(indent=2))
