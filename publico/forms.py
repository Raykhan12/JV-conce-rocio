from django import forms
from solicitudes.models import SolicitudCertificado, DenunciaVecinal

_INPUT = {
    'class': (
        'w-full rounded-xl border border-gray-200 px-4 py-2.5 text-sm text-gray-800 bg-white '
        'focus:outline-none focus:border-green-500 focus:ring-2 focus:ring-green-200 '
        'transition placeholder-gray-400'
    )
}
_SELECT = {
    'class': (
        'w-full rounded-xl border border-gray-200 bg-white px-4 py-2.5 text-sm text-gray-800 '
        'focus:outline-none focus:border-green-500 focus:ring-2 focus:ring-green-200 transition'
    )
}
_TEXTAREA = {
    'class': (
        'w-full rounded-xl border border-gray-200 px-4 py-2.5 text-sm text-gray-800 bg-white '
        'focus:outline-none focus:border-green-500 focus:ring-2 focus:ring-green-200 '
        'transition placeholder-gray-400 resize-none'
    )
}


class CertificadoForm(forms.ModelForm):
    autorizado = forms.BooleanField(
        label='Autorizo a la Junta de Vecinos a utilizar mis datos personales exclusivamente para esta solicitud.',
        required=True,
    )

    class Meta:
        model  = SolicitudCertificado
        fields = [
            'nombre', 'rut', 'direccion', 'telefono', 'email',
            'canal', 'motivo', 'motivo_otro',
            'es_socio', 'boleta_servicio',
            'autorizado',
        ]
        widgets = {
            'nombre':      forms.TextInput(attrs={**_INPUT, 'placeholder': 'Ej: Juan Pérez González'}),
            'rut':         forms.TextInput(attrs={**_INPUT, 'placeholder': 'Ej: 12.345.678-9'}),
            'direccion':   forms.TextInput(attrs={**_INPUT, 'placeholder': 'Calle y número'}),
            'telefono':    forms.TextInput(attrs={**_INPUT, 'placeholder': '+56 9 1234 5678'}),
            'email':       forms.EmailInput(attrs={**_INPUT, 'placeholder': 'correo@ejemplo.com'}),
            'canal':       forms.Select(attrs=_SELECT),
            'motivo':      forms.Select(attrs=_SELECT),
            'motivo_otro': forms.TextInput(attrs={**_INPUT, 'placeholder': 'Especifique el motivo'}),
        }

    def clean(self):
        cleaned = super().clean()
        es_socio = cleaned.get('es_socio')
        boleta   = cleaned.get('boleta_servicio')
        if es_socio is False and not boleta:
            self.add_error('boleta_servicio',
                           'Debe adjuntar una boleta de servicio (luz o agua) si no es socio/a.')
        motivo = cleaned.get('motivo')
        if motivo == 'OTRO' and not cleaned.get('motivo_otro'):
            self.add_error('motivo_otro', 'Por favor especifique el motivo.')
        return cleaned


class DenunciaForm(forms.ModelForm):
    horario = forms.MultipleChoiceField(
        label='Horario en que ocurre',
        choices=DenunciaVecinal.HORARIO_CHOICES,
        widget=forms.CheckboxSelectMultiple,
        required=False,
    )

    class Meta:
        model  = DenunciaVecinal
        fields = [
            'nombre', 'direccion', 'telefono', 'email',
            'categoria',
            'descripcion', 'ubicacion', 'horario', 'ocurrido_antes',
            'urgencia',
            'desc_evidencia', 'notas_adicionales',
        ]
        widgets = {
            'nombre':    forms.TextInput(attrs={'placeholder': 'Ej: María González'}),
            'direccion': forms.TextInput(attrs={'placeholder': 'Calle y número'}),
            'telefono':  forms.TextInput(attrs={'placeholder': '+56 9 1234 5678'}),
            'email':     forms.EmailInput(attrs={'placeholder': 'correo@ejemplo.com (opcional)'}),
            'descripcion':    forms.Textarea(attrs={'rows': 4, 'placeholder': 'Explique qué ocurre, desde cuándo, y cómo afecta a la comunidad.'}),
            'ubicacion':      forms.TextInput(attrs={'placeholder': 'Calle, pasaje, intersección o punto de referencia exacto.'}),
            'ocurrido_antes': forms.Textarea(attrs={'rows': 2, 'placeholder': '¿Ha ocurrido antes? ¿Cuándo fue la última vez?'}),
            'desc_evidencia':     forms.Textarea(attrs={'rows': 2, 'placeholder': 'Describa qué tipo de evidencia tiene (fotos, videos, testigos).'}),
            'notas_adicionales':  forms.Textarea(attrs={'rows': 2, 'placeholder': '¿Algo más que quiera agregar?'}),
        }
