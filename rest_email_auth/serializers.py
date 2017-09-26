"""Serializers for the ``rest_email_auth`` app.

The serializers handle the conversion of data between the JSON or form
data the API receives and native Python datatypes.
"""

from django.contrib.auth import get_user_model, password_validation
from django.utils.translation import ugettext_lazy as _

from rest_framework import serializers

from rest_email_auth import models


UserModel = get_user_model()


class EmailVerificationSerializer(serializers.Serializer):
    """
    Serializer for verifying an email address.
    """
    email = serializers.EmailField(read_only=True)
    key = serializers.CharField(write_only=True)
    password = serializers.CharField(
        style={'input_type': 'password'},
        write_only=True)

    def save(self):
        """
        Confirm the email address matching the confirmation key.
        """
        self._confirmation.confirm()

    def validate(self, data):
        """
        Validate the provided data.

        Returns:
            dict:
                The validated data.

        Raises:
            serializers.ValidationError:
                If the provided password is invalid.
        """
        user = self._confirmation.email.user

        if not user.check_password(data['password']):
            raise serializers.ValidationError(
                _('The provided password is invalid.'))

        # Add email to returned data
        data['email'] = self._confirmation.email.email

        return data

    def validate_key(self, key):
        """
        Validate the provided confirmation key.

        Returns:
            str:
                The validated confirmation key.

        Raises:
            serializers.ValidationError:
                If there is no email confirmation with the given key or
                the confirmation has expired.
        """
        try:
            confirmation = models.EmailConfirmation.objects.select_related(
                'email__user').get(key=key)
        except models.EmailConfirmation.DoesNotExist:
            raise serializers.ValidationError(
                _('The provided verification key is invalid.'))

        if confirmation.is_expired:
            raise serializers.ValidationError(
                _('That verification code has expired.'))

        # Cache confirmation instance
        self._confirmation = confirmation

        return key


class RegistrationSerializer(serializers.ModelSerializer):
    """
    Serializer for registering new users.
    """
    email = serializers.EmailField()

    class Meta(object):
        extra_kwargs = {
            'password': {
                'style': {'input_type': 'password'},
                'write_only': True,
            },
        }
        fields = (UserModel.USERNAME_FIELD, 'email', 'password')
        model = UserModel

    def create(self, validated_data):
        """
        Create a new user from the data passed to the serializer.

        If the provided email has not been verified yet, the user is
        created and a verification email is sent to the address.
        Otherwise we send a notification to the email address that
        someone attempted to register with an email that's already been
        verified.

        Args:
            validated_data (dict):
                The data passed to the serializer after it has been
                validated.

        Returns:
            A new user created from the provided data.
        """
        email = validated_data.pop('email')
        password = validated_data.pop('password')

        user = UserModel(**validated_data)
        user.set_password(password)

        # We set an ephemeral email property so that it is included in
        # the data returned by the serializer.
        user.email = email

        email_query = models.EmailAddress.objects.filter(
            email=email,
            is_verified=True)

        if email_query.exists():
            existing_email = email_query.get()
            existing_email.send_duplicate_signup()
        else:
            user.save()

            email_instance = models.EmailAddress.objects.create(
                email=email,
                user=user)
            email_instance.send_confirmation()

        return user

    def validate_password(self, password):
        """
        Validate the provided password.

        Args:
            password (str):
                The password provided by the user.

        Returns:
            str:
                The validated password.

        Raises:
            ValidationError:
                If the provided password doesn't pass Django's provided
                password validation.
        """
        password_validation.validate_password(password)

        return password
