# knowledge_graph/urls.py or graphapp/urls.py (recommended to use app-level)
from django.urls import path
from graphapp import views

urlpatterns = [
    path('', views.input_form, name='home'),  # Root URL renders the form
]

