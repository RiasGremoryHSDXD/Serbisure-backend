from django.apps import AppConfig
from django.db.models.signals import post_migrate
import os

def generate_models_markdown(sender, **kwargs):
    from django.apps import apps
    from django.conf import settings
    
    app_names = ['accounts', 'verifications', 'booking', 'reviews', 'notifications', 'chat']
    markdown = "# Serbisure Database Models\n\nThis document outlines the database schema, models, field types, and choices (enums) used in the Serbisure backend.\n\n"
    
    for app_name in app_names:
        try:
            app_config = apps.get_app_config(app_name)
        except LookupError:
            continue
            
        app_models = app_config.get_models()
        models_list = list(app_models)
        if not models_list:
            continue
            
        markdown += f"## {app_name.capitalize()} App\n\n"
        
        for model in models_list:
            markdown += f"### `{model.__name__}`\n"
            markdown += f"- **Database Table:** `{model._meta.db_table}`\n\n"
            markdown += "| Field Name | Data Type | Constraints / Choices / FK |\n"
            markdown += "| --- | --- | --- |\n"
            
            for field in model._meta.fields:
                field_name = field.name
                field_type = field.__class__.__name__
                constraints = []
                if field.primary_key: constraints.append("Primary Key")
                if field.unique: constraints.append("Unique")
                if field.null: constraints.append("Null=True")
                if field.blank: constraints.append("Blank=True")
                if field.is_relation and field.related_model:
                    constraints.append(f"FK -> `{field.related_model.__name__}`")
                if field.choices:
                    choices_str = ", ".join([f"'{c[0]}'" for c in field.choices])
                    constraints.append(f"Choices: [{choices_str}]")
                    
                constraint_str = ", ".join(constraints) if constraints else "-"
                markdown += f"| `{field_name}` | `{field_type}` | {constraint_str} |\n"
            markdown += "\n"
            
    docs_path = os.path.join(settings.BASE_DIR, 'docs', 'MODELS_REFERENCE.md')
    os.makedirs(os.path.dirname(docs_path), exist_ok=True)
    with open(docs_path, "w", encoding="utf-8") as f:
        f.write(markdown)
    print(f"\n[Auto-Docs] Successfully updated {docs_path}!")


class AccountsConfig(AppConfig):
    name = 'accounts'

    def ready(self):
        # This tells Django to run the function right after 'python manage.py migrate' finishes!
        post_migrate.connect(generate_models_markdown, sender=self)
