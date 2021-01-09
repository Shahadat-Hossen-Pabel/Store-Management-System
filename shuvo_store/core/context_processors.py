from .models import ProductCategory
from django.db.models import Q

def category_menu(request):
	category = ProductCategory.objects.all()

	return {
		'category': category
	}