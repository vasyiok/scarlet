import hashlib

from django import forms
from django.utils.translation import ugettext_lazy as _
from django.contrib.auth import authenticate
from django.contrib.auth.models import Group
from django.utils.safestring import mark_safe

from . import settings as accounts_settings
from .models import AccountsSignup
from .utils import get_profile_model, get_user_model

import random

attrs_dict = {'class': 'required'}

USERNAME_RE = r'^[\.\w]+$'


class PasswordLinkWidget(forms.Widget):
    def render(self, name, value, attrs=None):
        return mark_safe(u'<a href="../password/" id="password-link">Change</a>')


class UserForm(forms.ModelForm):
    password = forms.CharField(required=False, widget=PasswordLinkWidget())
    groups = forms.ModelMultipleChoiceField(required=False,
                queryset=Group.objects.all().order_by('name'))

    def clean(self):
        if self.is_valid():
            self.cleaned_data['password'] = self.instance.password
            return self.cleaned_data

        if hasattr(self, 'cleaned_data'):
            return self.cleaned_data
        else:
            return {}

    class Meta:
        model = get_user_model()


class SignupFormMixin(object):
    """
    Form for creating a new user account.
    Validates that the requested username and e-mail is not already in use.
    Also requires the password to be entered twice.
    """
    first_name = forms.CharField(label=_('First name'), max_length=30)
    last_name = forms.CharField(label=_('Last name'), max_length=30)
    username = forms.RegexField(regex=USERNAME_RE,
                                max_length=30,
                                widget=forms.TextInput(attrs=attrs_dict),
                                label=_("Username"),
                                error_messages={'invalid': _('Username must contain only letters, numbers, dots and underscores.')})
    email = forms.EmailField(widget=forms.TextInput(attrs=dict(attrs_dict,
                                                               maxlength=75)),
                             label=_("Email"))
    password1 = forms.CharField(widget=forms.PasswordInput(attrs=attrs_dict,
                                                           render_value=False),
                                label=_("Create password"))
    password2 = forms.CharField(widget=forms.PasswordInput(attrs=attrs_dict,
                                                           render_value=False),
                                label=_("Repeat password"))

    def clean_username(self):
        """
        Validate that the username is alphanumeric and is not already in use.
        Also validates that the username is not listed in
        ACCOUNTS_FORBIDDEN_USERNAMES list.
        """
        try:
            get_user_model().objects.get(
                username__iexact=self.cleaned_data['username'])
        except get_user_model().DoesNotExist:
            pass
        else:
            raise forms.ValidationError(_('This username is already taken.'))
        if self.cleaned_data['username'].lower() in accounts_settings.ACCOUNTS_FORBIDDEN_USERNAMES:
            raise forms.ValidationError(_('This username is not allowed.'))
        return self.cleaned_data['username']

    def clean_email(self):
        """
        Validate that the e-mail address is unique.
        """
        if get_user_model().objects.filter(
            email__iexact=self.cleaned_data['email']):
            raise forms.ValidationError(_('This email is already in use. Please supply a different email.'))
        return self.cleaned_data['email']

    def clean(self):
        """
        Validates that the values entered into the two password fields match.
        Note that an error here will end up in ``non_field_errors()`` because
        it doesn't apply to a single field.
        """
        if 'password1' in self.cleaned_data and 'password2' in self.cleaned_data:
            if self.cleaned_data['password1'] != self.cleaned_data['password2']:
                raise forms.ValidationError(_('The two password fields didn\'t match.'))
        return self.cleaned_data

    def save(self):
        """ Creates a new user and account. Returns the newly created user. """
        username, email, password, first_name, last_name = (self.cleaned_data['username'],
                                     self.cleaned_data['email'],
                                     self.cleaned_data['password1'],
                                     self.cleaned_data['first_name'],
                                     self.cleaned_data['last_name'],)

        new_user = AccountsSignup.objects.create_user(username,
                                                     email,
                                                     password,
                                                     first_name,
                                                     last_name,
                                                     not accounts_settings.ACCOUNTS_ACTIVATION_REQUIRED,
                                                     accounts_settings.ACCOUNTS_ACTIVATION_REQUIRED,
                                                     accounts_settings.ACCOUNTS_WELCOME_EMAIL)
        return new_user


class SignupForm(forms.Form, SignupFormMixin):
    pass


class SignupModelForm(forms.ModelForm, SignupFormMixin):
    password1 = forms.CharField(widget=forms.PasswordInput(attrs=attrs_dict,
                                                           render_value=False),
                                label=_("Create password"))
    password2 = forms.CharField(widget=forms.PasswordInput(attrs=attrs_dict,
                                                           render_value=False),
                                label=_("Repeat password"))

    def __init__(self, *args, **kwargs):
        """ Set placeholder password to avert validation issues. """
        kwargs.update(initial={'password': 'placeholder'})
        super(SignupModelForm, self).__init__(*args, **kwargs)

    def clean(self):
        return SignupFormMixin.clean(self)

    def save(self, *args, **kwargs):
        return SignupFormMixin.save(self)

    class Meta:
        model = get_user_model()
        fields = ('first_name', 'last_name', 'username',
                  'email', 'password1', 'password2')
        widgets = {'password': forms.HiddenInput()}


class SignupFormOnlyEmail(SignupForm):
    """
    Form for creating a new user account but not needing a username.

    This form is an adaptation of :class:`SignupForm`. It's used when
    ACCOUNTS_WITHOUT_USERNAME setting is set to True. And thus the user
    is not asked to supply an username, but one is generated for them. The user
    can than keep sign in by using their email.
    """
    def __init__(self, *args, **kwargs):
        super(SignupFormOnlyEmail, self).__init__(*args, **kwargs)
        del self.fields['username']

    def save(self):
        """
        Generate a random username before falling back to parent signup form
        """
        while True:
            username = hashlib.sha1(str(random.random())).hexdigest()[:5]
            try:
                get_user_model().objects.get(username__iexact=username)
            except get_user_model().DoesNotExist:
                break

        self.cleaned_data['username'] = username
        return super(SignupFormOnlyEmail, self).save()


class SignupFormTos(SignupForm):
    """ Add a Terms of Service button to the ``SignupForm``. """
    tos = forms.BooleanField(widget=forms.CheckboxInput(attrs=attrs_dict),
                             label=_(u'I have read and agree to the Terms of Service'),
                             error_messages={'required': _('You must agree to the terms to register.')})


def identification_field_factory(label, error_required):
    """
    A simple identification field factory which enable you to set the label.

    :param label:
        String containing the label for this field.

    :param error_required:
        String containing the error message if the field is left empty.
    """
    return forms.CharField(label=label,
                           widget=forms.TextInput(attrs=attrs_dict),
                           max_length=75,
                           error_messages={'required': _("%(error)s") % {'error': error_required}})


class AuthenticationForm(forms.Form):
    """
    A custom form where the identification can be a e-mail address or username.
    """
    identification = identification_field_factory(_(u"Email or username"),
                                                  _(u"Either supply us with your email or username."))
    password = forms.CharField(label=_("Password"),
                               widget=forms.PasswordInput(attrs=attrs_dict, render_value=False))
    remember_me = forms.BooleanField(widget=forms.CheckboxInput(),
                                     required=False,
                                     label=_(u'Remember me for %(days)s') % {'days': _(accounts_settings.ACCOUNTS_REMEMBER_ME_DAYS[0])})

    def __init__(self, *args, **kwargs):
        """
        A custom init because we need to change the label if no
        username is used
        """
        super(AuthenticationForm, self).__init__(*args, **kwargs)
        # Dirty hack, somehow the label doesn't get translated without declaring
        # it again here.
        self.fields['remember_me'].label = _(u'Remember me for %(days)s') % {'days': _(accounts_settings.ACCOUNTS_REMEMBER_ME_DAYS[0])}
        if accounts_settings.ACCOUNTS_WITHOUT_USERNAMES:
            self.fields['identification'] = identification_field_factory(_(u"Email"),
                                                                         _(u"Please supply your email."))

    def clean(self):
        """
        Checks for the identification and password.

        If the combination can't be found will raise an invalid sign in error.
        """
        identification = self.cleaned_data.get('identification')
        password = self.cleaned_data.get('password')

        if identification and password:
            user = authenticate(identification=identification,
                                password=password)
            if user is None:
                raise forms.ValidationError(_(u"Please enter a correct username or email and password. Note that both fields are case-sensitive."))
        return self.cleaned_data


class ChangeEmailForm(forms.Form):
    email = forms.EmailField(widget=forms.TextInput(attrs=dict(attrs_dict,
                                                               maxlength=75)),
                             label=_(u"New email"))

    def __init__(self, user, *args, **kwargs):
        """
        The current ``user`` is needed for initialisation of this form so
        that we can check if the email address is still free and not always
        returning ``True`` for this query because it's the users own e-mail
        address.
        """
        super(ChangeEmailForm, self).__init__(*args, **kwargs)
        if not isinstance(user, get_user_model()):
            raise TypeError, "user must be an instance of %s" % get_user_model().__name__
        else:
            self.user = user

    def clean_email(self):
        """
        Validate that the email is not already registered with another user
        """
        if self.cleaned_data['email'].lower() == self.user.email:
            raise forms.ValidationError(_(u'You\'re already known under this email.'))
        if get_user_model().objects.filter(email__iexact=self.cleaned_data['email']).exclude(email__iexact=self.user.email):
            raise forms.ValidationError(_(u'This email is already in use. Please supply a different email.'))
        return self.cleaned_data['email']

    def save(self):
        """
        Save method calls :func:`user.change_email()` method which sends out an
        email with an verification key to verify and with it enable this new
        email address.

        """
        return self.user.accounts_signup.change_email(self.cleaned_data['email'])


class EditProfileForm(forms.ModelForm):
    """
    Base form used for fields that are always required
    """
    first_name = forms.CharField(label=_(u'First name'),
                                 max_length=30,
                                 required=False)
    last_name = forms.CharField(label=_(u'Last name'),
                                max_length=30,
                                required=False)

    def __init__(self, *args, **kw):
        super(EditProfileForm, self).__init__(*args, **kw)
        # Put the first and last name at the top
        new_order = self.fields.keyOrder[:-2]
        new_order.insert(0, 'first_name')
        new_order.insert(1, 'last_name')
        self.fields.keyOrder = new_order

    class Meta:
        model = get_profile_model()
        exclude = ['user']

    def save(self, force_insert=False, force_update=False, commit=True):
        profile = super(EditProfileForm, self).save(commit=commit)
        # Save first and last name
        user = profile.user
        user.first_name = self.cleaned_data['first_name']
        user.last_name = self.cleaned_data['last_name']
        user.save()

        return profile
