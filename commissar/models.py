from django.db import models
from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver

# Create your models here.


class Commissar (models.Model):

    LEVEL = (('UCI rozhodčí', 'UCI rozhodčí'), ('Elite National Commissar', 'Elite National Commissar'), ('Národní rozhodčí', 'Národní rozhodčí'), ('',''))

    first_name = models.CharField(max_length=200, null=True, blank=True)
    last_name = models.CharField(max_length=200)

    photo = models.ImageField(
        upload_to='static/images/commissar/', blank=True, null=True, default='static/images/users/blank-avatar-200x200.jpg')


    level = models.CharField(max_length=100, choices=LEVEL, default="Národní rozhodčí", null=True, blank=True)

    class Meta:
        verbose_name = "Rozhodčí"
        verbose_name_plural = 'Rozhodčí'
    
    def __str__(self):
        return (f"{self.last_name} {self.first_name}")
    
# vymazání staré fotky jezdce při její změně
@receiver(pre_save, sender=Commissar)
def delete_file_on_change_extension(sender, instance, **kwargs):
    if instance.pk:
        try:
            old_photo = Commissar.objects.get(pk=instance.pk).photo
        except Commissar.DoesNotExist:
            return
        else:
            new_photo = instance.photo
            if old_photo == "static/images/commissar/uni.jpeg":
                return
            if old_photo and old_photo.url != new_photo.url:
                old_photo.delete(save=False)
pre_save.connect(delete_file_on_change_extension, sender=Commissar)

