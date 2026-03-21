from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import RequestFactory
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from bmx.context_processors import navbar_context
from event.models import Event
from .models import CommissionTask


User = get_user_model()


class CommissionTaskModelTests(TestCase):
    def test_completed_timestamp_is_set_for_done_task(self):
        task = CommissionTask.objects.create(
            title="Dopsat propozice",
            status=CommissionTask.STATUS_DONE,
        )

        self.assertIsNotNone(task.completed_at)

    def test_completed_timestamp_is_cleared_when_task_is_reopened(self):
        task = CommissionTask.objects.create(
            title="Dopsat propozice",
            status=CommissionTask.STATUS_DONE,
        )

        task.status = CommissionTask.STATUS_IN_PROGRESS
        task.save()

        self.assertIsNone(task.completed_at)

    def test_task_can_exist_without_related_event(self):
        task = CommissionTask.objects.create(
            title="Domluvit briefing rozhodčích",
            status=CommissionTask.STATUS_NEW,
        )

        self.assertIsNone(task.event)

    def test_task_can_be_linked_to_event(self):
        event = Event.objects.create(
            name="Openseason 2026",
            date=timezone.localdate(),
            type_for_ranking="Volný závod",
        )

        task = CommissionTask.objects.create(
            title="Připravit checklist pro závod",
            event=event,
            status=CommissionTask.STATUS_NEW,
        )

        self.assertEqual(task.event, event)


class CommissionTaskViewTests(TestCase):
    def setUp(self):
        self.commission_user = User.objects.create_user(
            first_name="Komise",
            last_name="Clen",
            username="komise",
            email="komise@example.com",
            password="StrongPass123!",
        )
        self.commission_user.is_active = True
        self.commission_user.is_commission = True
        self.commission_user.save()

        self.other_user = User.objects.create_user(
            first_name="Bezny",
            last_name="Uzivatel",
            username="bezny",
            email="bezny@example.com",
            password="StrongPass123!",
        )
        self.other_user.is_active = True
        self.other_user.save()

        self.mine_task = CommissionTask.objects.create(
            title="Zkontrolovat kalendar",
            assignee=self.commission_user,
            status=CommissionTask.STATUS_NEW,
            due_date=timezone.localdate() + timedelta(days=3),
        )
        self.overdue_task = CommissionTask.objects.create(
            title="Dodat podklady",
            assignee=self.commission_user,
            status=CommissionTask.STATUS_IN_PROGRESS,
            due_date=timezone.localdate() - timedelta(days=1),
        )
        self.done_task = CommissionTask.objects.create(
            title="Uzavrit zapis",
            assignee=self.commission_user,
            status=CommissionTask.STATUS_DONE,
        )
        self.event = Event.objects.create(
            name="Openseason 2026",
            date=timezone.localdate(),
            type_for_ranking="Volný závod",
        )
        self.task_with_event = CommissionTask.objects.create(
            title="Připravit podklady pro briefing",
            assignee=self.commission_user,
            event=self.event,
            status=CommissionTask.STATUS_NEW,
        )

    def test_commission_member_can_open_task_board(self):
        self.client.force_login(self.commission_user)

        response = self.client.get(reverse("todo:task-list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ukoly komise BMX")
        self.assertContains(response, self.mine_task.title)

    def test_regular_user_is_redirected_from_task_board(self):
        self.client.force_login(self.other_user)

        response = self.client.get(reverse("todo:task-list"))

        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_staff_without_commission_role_is_redirected_from_task_board(self):
        self.other_user.is_staff = True
        self.other_user.save()
        self.client.force_login(self.other_user)

        response = self.client.get(reverse("todo:task-list"))

        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_overdue_filter_shows_only_overdue_open_tasks(self):
        self.client.force_login(self.commission_user)

        response = self.client.get(reverse("todo:task-list"), {"scope": "overdue"})

        self.assertContains(response, self.overdue_task.title)
        self.assertNotContains(response, self.mine_task.title)
        self.assertNotContains(response, self.done_task.title)

    def test_task_board_shows_related_event_only_when_present(self):
        self.client.force_login(self.commission_user)

        response = self.client.get(reverse("todo:task-list"))

        self.assertContains(response, self.task_with_event.title)
        self.assertContains(response, "Závod: Openseason 2026")


class NavbarTaskBadgeTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_navbar_context_marks_overdue_tasks_red(self):
        user = User.objects.create_user(
            first_name="Navbar",
            last_name="Komise",
            username="navbar_komise",
            email="navbar@example.com",
            password="StrongPass123!",
        )
        user.is_active = True
        user.is_commission = True
        user.save()

        CommissionTask.objects.create(
            title="Po terminu",
            assignee=user,
            status=CommissionTask.STATUS_IN_PROGRESS,
            due_date=timezone.localdate() - timedelta(days=1),
        )

        request = self.factory.get("/")
        request.user = user

        context = navbar_context(request)

        self.assertEqual(context["navbar_task_count"], 1)
        self.assertTrue(context["navbar_task_has_overdue"])

    def test_navbar_context_marks_future_tasks_green(self):
        user = User.objects.create_user(
            first_name="Navbar2",
            last_name="Komise",
            username="navbar_komise2",
            email="navbar2@example.com",
            password="StrongPass123!",
        )
        user.is_active = True
        user.is_commission = True
        user.save()

        CommissionTask.objects.create(
            title="Pred terminem",
            assignee=user,
            status=CommissionTask.STATUS_NEW,
            due_date=timezone.localdate() + timedelta(days=3),
        )

        request = self.factory.get("/")
        request.user = user

        context = navbar_context(request)

        self.assertEqual(context["navbar_task_count"], 1)
        self.assertFalse(context["navbar_task_has_overdue"])
