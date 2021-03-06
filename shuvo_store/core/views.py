from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import render,get_object_or_404,redirect
from django.views.generic import DetailView,ListView
from django.core.exceptions import ObjectDoesNotExist
from django.views import View
from django.utils import timezone
from django.contrib import messages
from .forms import CheckoutForm,CouponForm
from .models import (
	Product,
	ProductCategory,
	OrderProduct,
	Order,
	Address,
	Cupon,
	Payment
)
import random
import string
import stripe
stripe.api_key = settings.STRIPE_SECRET_KEY

def create_ref_code():
	return ''.join(random.choices(string.ascii_lowercase + string.digits, k=20))


def is_valid_form(values):
	valid = True
	for field in values:
		if field == '':
			valid = False
	return valid


class HomeView(ListView):
	model = Product
	template_name = 'home.html'

class AllProductView(ListView):
	model = Product
	template_name = 'all_products.html'

class ShopView(DetailView):
	model = ProductCategory
	template_name = 'shop.html'

	def get_context_data(self, *args, **kwargs):
		context = super().get_context_data(*args, **kwargs)
		obj = self.get_object()
		category_set = obj.product_set.all()
		context["category_set"] = category_set
		return context

class ProductDetailView(DetailView):
	model = Product
	template_name = 'product_detail.html'


class CartView(View,LoginRequiredMixin):
	def get(self,request,*args,**kwargs):
		try:
			order = Order.objects.get(user=self.request.user,ordered=False)
			context = {
				'object': order,
			}
			return render(self.request,'cart.html',context)
		except ObjectDoesNotExist:
			messages.error(self.request,'You do not have active order')
			return redirect("/")

class PaymentView(View,LoginRequiredMixin):
	def get(self,request,*args,**kwargs):
		order = Order.objects.get(user=self.request.user, ordered=False)
		if order.billing_address:
			context = {
				'order': order,
				'DISPLAY_COUPON_FORM':False
			}
			return render(self.request,'payment.html',context)
		else:
			messages.warning(self.request,'You have not added billing_address')
			return redirect("core_main:checkout")


	def post(self,request, *args, **kwargs):
		order = Order.objects.get(user=self.request.user, ordered=False)
		token = self.request.POST.get('stripeToken')
		amount= int(order.get_total() * 100)
				
		try:
		     # charge once off on the token
			charge = stripe.Charge.create(
                amount=amount,  # cents
                currency="usd",
                source=token
            )
            # create the payment
			payment = Payment()
			payment.stripe_charge_id = charge['id']
			payment.user = self.request.user
			payment.amount = order.get_total()
			payment.save()

            # assign the payment to the order
			order_items = order.items.all()
			order_items.update(ordered=True)
			for item in order_items:
				item.save()


			order.ordered = True
			order.payment = payment
			#TODO: assign ref code.
			order.ref_code = create_ref_code()
			order.save()
			messages.info(self.request,"Your order was successfull")
			return redirect("/")

		except stripe.error.CardError as e:
			body = e.json_body
			err = body.get('erroe',{})
			messages.warning(self.request,f"{err.get('message')}")
			return redirect("/")
		except stripe.error.RateLimitError as e:
			# Too many requests made to the API too quickly
			messages.warning(self.request,"Rate Limit Error")
			return redirect("/")
		except stripe.error.InvalidRequestError as e:
			# Invalid parameters were supplied to Stripe's API
			messages.warning(self.request,"Invalid parameters")
			return redirect("/")
		except stripe.error.AuthenticationError as e:
			# Authentication with Stripe's API failed
			# (maybe you changed API keys recently)
			messages.warning(self.request,"Not Authenticated")
			return redirect("/")
		except stripe.error.APIConnectionError as e:
			# Network communication with Stripe failed
			messages.warning(self.request,"Network Error")
			return redirect("/")
		except stripe.error.StripeError as e:
			# Display a very generic error to the user, and maybe send
			# yourself an email
			messages.warning(self.request,"Something went wrong.You were not chaarged.Plz try again")
			return redirect("/")
		except Exception as e:
  			# Something else happened, completely unrelated to Stripe
  			messages.warning(self.request,"A serious error.we have been notified")
  			return redirect("/")


class BikashView(View,LoginRequiredMixin):
	def get(self,request,*args,**kwargs):
		order = Order.objects.get(user=self.request.user, ordered=False)
		if order.billing_address:
			context = {
				'order': order,
				'DISPLAY_COUPON_FORM':False
			}
			return render(self.request,'bikash_payment.html',context)
		else:
			messages.warning(self.request,'You have not added billing_address')
			return redirect("core_main:checkout")

		#have post method..

class DbblView(View,LoginRequiredMixin):
	def get(self,request,*args,**kwargs):
		order = Order.objects.get(user=self.request.user, ordered=False)
		if order.billing_address:
			context = {
				'order': order,
				'DISPLAY_COUPON_FORM':False
			}
			return render(self.request,'dbbl_payment.html',context)
		else:
			messages.warning(self.request,'You have not added billing_address')
			return redirect("core_main:checkout")

		#have post method..




class CheckoutView(View,LoginRequiredMixin):
	def get(self,request,*args,**kwargs):
		try:
			order = Order.objects.get(user=self.request.user,ordered=False)
			form = CheckoutForm()
			context = {
				'order': order,
				'forms': form,
				'couponform': CouponForm(),
				'DISPLAY_COUPON_FORM': True
			}
			shipping_address_qs = Address.objects.filter(
				user = self.request.user,
				address_type = 'S',
				default=True
			)
			if shipping_address_qs.exists():
				context.update(
					{
						'default_shipping_address':shipping_address_qs[0]
					}
				)
			billing_address_qs = Address.objects.filter(
				user = self.request.user,
				address_type = 'B',
				default=True
			)
			if billing_address_qs.exists():
				context.update(
					{
						'default_billing_address':billing_address_qs[0]
					}
				)
			return render(self.request,'checkout.html',context)
		except ObjectDoesNotExist:
			messages.error(self.request,'You do not have active order')
			return redirect("/")


	def post(self,*args,**kwargs):
		form = CheckoutForm(self.request.POST or None)
		try:
			order = Order.objects.get(user=self.request.user,ordered=False)
			if form.is_valid():
				use_default_shipping = form.cleaned_data.get('use_default_shipping')
				if use_default_shipping:
					address_qs = Address.objects.filter(
						user = self.request.user,
						address_type = 'S',
						default=True
					)
					if address_qs.exists():
						shipping_address = address_qs[0]
						order.shipping_address = shipping_address
						order.save()
					else:
						messages.info(self.request, "No default shipping address available")
						return redirect('core_main:checkout')
				else:
					shipping_country = form.cleaned_data.get('shipping_country')
					shipping_address = form.cleaned_data.get('shipping_address')
					shipping_address2 = form.cleaned_data.get('shipping_address2')
					shipping_city = form.cleaned_data.get('shipping_city')
					shipping_zip_code = form.cleaned_data.get('shipping_zip_code')
					shipping_phone_number = form.cleaned_data.get('shipping_phone_number')
					shipping_email_address = form.cleaned_data.get('shipping_email_address')
					
					req_uired = [
						shipping_country,
						shipping_address,
						shipping_city,
						shipping_zip_code,
						shipping_phone_number,
						shipping_email_address
					]

					if is_valid_form(req_uired):
						shipping_address = Address(
							user = self.request.user,
							country = shipping_country,
							street_address = shipping_address,
							apartment_address = shipping_address2,
							city = shipping_city,
							zip_code = shipping_zip_code,
							phone = shipping_phone_number,
							email = shipping_email_address,
							address_type = 'S'
						)
						shipping_address.save()
						order.shipping_address = shipping_address
						order.save()
						set_default_shipping = form.cleaned_data.get('set_default_shipping')
						if set_default_shipping:
							shipping_address.default=True
							shipping_address.save()
					else:
						messages.info(self.request, "Please fill in the required shipping address")

				use_default_billing = form.cleaned_data.get('use_default_billing')
				same_billing_address = form.cleaned_data.get('same_billing_address')

				if same_billing_address:
					billing_address = shipping_address
					billing_address.pk = None
					billing_address.save()
					billing_address.address_type = 'B'
					billing_address.save()
					order.billing_address = billing_address
					order.save()

				elif use_default_billing:
					address_qs = Address.objects.filter(
						user = self.request.user,
						address_type='B',
						default=True
					)
					if address_qs.exists():
						billing_address = address_qs[0]
						order.billing_address = billing_address
						order.save()
					else:
						messages.info(self.request, "No default billing address available")
						return redirect('core_main:checkout')
				else:
					billing_country = form.cleaned_data.get('billing_country')
					billing_address = form.cleaned_data.get('billing_address')
					billing_address2 = form.cleaned_data.get('billing_address2')
					billing_city = form.cleaned_data.get('billing_city')
					billing_zip_code = form.cleaned_data.get('billing_zip_code')
					billing_phone_number = form.cleaned_data.get('billing_phone_number')
					billing_email_address = form.cleaned_data.get('billing_email_address')

					req_uired = [
						billing_country,
						billing_address,
						billing_city,
						billing_zip_code,
						billing_phone_number,
						billing_email_address
					]

					if is_valid_form(req_uired):
						billing_address = Address(
							user = self.request.user,
							country = billing_country,
							street_address = billing_address,
							apartment_address = billing_address2,
							city = billing_city,
							zip_code = billing_zip_code,
							phone = billing_phone_number,
							email = billing_email_address,
							address_type = 'B'
						)
						billing_address.save()
						order.billing_address = billing_address
						order.save()
						set_default_billing = form.cleaned_data.get('set_default_billing')
						if set_default_billing:
							billing_address.default=True
							billing_address.save()
					else:
						messages.info(self.request, "Please fill in the required billing address")
				

				payment_option = form.cleaned_data.get('payment_option')
					
				if payment_option == "S":
					return redirect('core_main:payment', payment_option='stripe')
				elif payment_option == "B":
					return redirect('core_main:bikash', payment_option='bikash')
				elif payment_option == "D":
					return redirect('core_main:dbbl', payment_option='dbbl')
				else:
					messages.warning(self.request,'Invalid payment option selected')
					return redirect('core_main:checkout')
		except ObjectDoesNotExist:
			messages.warning(self.request,'You do not have active order')
			return redirect("core_main:checkout")




@login_required()
def add_to_cart(request,slug):
	#get the product.
	take_product = get_object_or_404(Product, slug=slug)
	#create order product.
	create_order_product, created = OrderProduct.objects.get_or_create(
		item = take_product,
		user = request.user,
		ordered = False
	)
	#create_order_product.save()
	order_qs = Order.objects.filter(user = request.user, ordered=False)
	if order_qs.exists():
		order = order_qs[0]
		order_check = order.items.filter(item__slug = take_product.slug)
		#check if the order item is in the order.
		if create_order_product in order_check:
			create_order_product.quantity += 1
			create_order_product.save()
			messages.info(request,"This item quantity was updated")
			return redirect('core_main:cart')
		else:
			order.items.add(create_order_product)
			messages.info(request,"This inner item was added to your cart")
			return redirect('core_main:cart')
	else:
		date_of_order = timezone.now()
		order_var = Order.objects.create(user=request.user,ordered_date=date_of_order)
		order_var.items.add(create_order_product)
		messages.info(request,"This item was added to your cart")
	return redirect('core_main:cart')

@login_required()
def remove_from_cart(request,slug):
	#get_the_item
	take_product = get_object_or_404(Product, slug=slug)
	#return queryset
	order_qs = Order.objects.filter(user=request.user, ordered=False)
	if order_qs.exists():
		order = order_qs[0]
		order_check = order.items.filter(item__slug = take_product.slug)
		order_item_query = OrderProduct.objects.filter(
				item=take_product,
				user=request.user,
				ordered=False
			)[0]
		if order_item_query in order_check:
			order.items.remove(order_item_query)
			messages.info(request,"This item removed from  your cart")
			return redirect("core_main:cart")
		else:
			messages.info(request,"This item was not in your cart")
			return redirect("core_main:cart")

	else:
		messages.info(request,"you do not have active order")
		return redirect("core_main:cart")

@login_required()
def remove_single_item_from_cart(request,slug):
	#get the item.
	take_product = get_object_or_404(Product, slug=slug)
	#return queryset
	order_qs = Order.objects.filter(user=request.user, ordered=False)
	if order_qs.exists():
		order = order_qs[0]
		order_check = order.items.filter(item__slug = take_product.slug)
		order_item_query = OrderProduct.objects.filter(
				item=take_product,
				user=request.user,
				ordered=False
			)[0]

		if order_item_query.quantity > 1:
			order_item_query.quantity -= 1
			order_item_query.save()
			messages.info(request,"One item was removed from your cart")
			return redirect("core_main:cart")
		else:
			order.items.remove(order_item_query)
			messages.info(request,"This item was not in your cart")
			return redirect("core_main:cart")
	else:
		messages.info(request,"you do not have active order")
		return redirect("core_main:cart")


def get_coupon(request, code):
	try:
		coupon = Cupon.objects.get(code=code)
		return coupon
	except ObjectDoesNotExist:
		messages.info(request, "This coupon does not exist")
		return redirect("core_main:checkout")


class AddCouponView(View,LoginRequiredMixin):
	def post(self, *args, **kwargs):
		form = CouponForm(self.request.POST or None)
		if form.is_valid():
			try:
				code = form.cleaned_data.get('code')
				order = Order.objects.get(user=self.request.user, ordered=False)
				order.coupon = get_coupon(self.request, code)
				order.save()
				messages.success(self.request, "successfully added coupon")
				return redirect("core_main:checkout")
			except ObjectDoesNotExist:
				messages.info(self.request, "you do not have active order")
				return redirect("core_main:checkout")
		#TODO:raise error
		return None



def contact_view(request):
	return render(request,'contact.html')

def about_view(request):
	return render(request,'about.html')

def blog_view(request):
	return render(request,'blog.html')