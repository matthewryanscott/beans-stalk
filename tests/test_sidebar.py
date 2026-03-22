from beans.models import Bean, BeanId
from beans_stalk.config import StalkConfig
from beans_stalk.ui.sidebar import Sidebar


def _bean(title="Test", status="open", assignee=None, priority=2, body=""):
    return Bean(
        id=BeanId.generate(),
        title=title,
        status=status,
        assignee=assignee,
        priority=priority,
        body=body,
    )


class TestSidebar:
    def test_show_bean_populates_fields(self, qtbot):
        sidebar = Sidebar(StalkConfig())
        qtbot.addWidget(sidebar)
        bean = _bean(title="My Task", priority=1, assignee="alice", body="Description")
        sidebar.show_bean(bean, [])
        assert sidebar._title_edit.text() == "My Task"
        assert sidebar._priority_spin.value() == 1
        assert sidebar._assignee_label.text() == "alice"
        assert sidebar._body_edit.toPlainText() == "Description"

    def test_new_bean_mode_clears_fields(self, qtbot):
        sidebar = Sidebar(StalkConfig())
        qtbot.addWidget(sidebar)
        sidebar.show_bean(_bean(title="Existing"), [])
        sidebar.start_new_bean()
        assert sidebar._title_edit.text() == ""
        assert sidebar._priority_spin.value() == 2
        assert sidebar._save_btn.text() == "Create"
        assert sidebar._creating is True

    def test_new_bean_with_prefill(self, qtbot):
        sidebar = Sidebar(StalkConfig())
        qtbot.addWidget(sidebar)
        sidebar.start_new_bean({"parent_id": "bean-00000001"})
        assert sidebar._parent_edit.text() == "bean-00000001"

    def test_save_emits_signal_for_existing(self, qtbot):
        sidebar = Sidebar(StalkConfig())
        qtbot.addWidget(sidebar)
        bean = _bean(title="Original")
        sidebar.show_bean(bean, [])
        sidebar._title_edit.setText("Updated")
        with qtbot.waitSignal(sidebar.save_requested, timeout=1000) as blocker:
            sidebar._save_btn.click()
        assert blocker.args[0] == bean.id
        assert blocker.args[1]["title"] == "Updated"
        # BeanUpdate-only fields: no assignee, ref_id, or status
        assert "assignee" not in blocker.args[1]
        assert "ref_id" not in blocker.args[1]
        assert "status" not in blocker.args[1]

    def test_create_emits_signal_for_new(self, qtbot):
        sidebar = Sidebar(StalkConfig())
        qtbot.addWidget(sidebar)
        sidebar.start_new_bean()
        sidebar._title_edit.setText("New Task")
        with qtbot.waitSignal(sidebar.create_bean_requested, timeout=1000) as blocker:
            sidebar._save_btn.click()
        assert blocker.args[0]["title"] == "New Task"

    def test_status_message(self, qtbot):
        sidebar = Sidebar(StalkConfig())
        qtbot.addWidget(sidebar)
        sidebar.show_status("Something went wrong")
        assert sidebar._status_label.isVisible()
        assert sidebar._status_label.text() == "Something went wrong"

    def test_status_read_only_for_existing(self, qtbot):
        sidebar = Sidebar(StalkConfig())
        qtbot.addWidget(sidebar)
        bean = _bean(status="in_progress")
        sidebar.show_bean(bean, [])
        assert sidebar._status_label_field.currentText() == "in_progress"

    def test_assignee_read_only_for_existing(self, qtbot):
        sidebar = Sidebar(StalkConfig())
        qtbot.addWidget(sidebar)
        bean = _bean(assignee="bob")
        sidebar.show_bean(bean, [])
        assert sidebar._assignee_label.text() == "bob"

    def test_ref_id_read_only_for_existing(self, qtbot):
        sidebar = Sidebar(StalkConfig())
        qtbot.addWidget(sidebar)
        bean = _bean()
        bean = Bean(id=bean.id, title="T", ref_id="GH-123")
        sidebar.show_bean(bean, [])
        assert sidebar._ref_id_display.text() == "GH-123"
        assert not sidebar._ref_id_edit.isVisible()

    def test_ref_id_editable_for_new(self, qtbot):
        sidebar = Sidebar(StalkConfig())
        qtbot.addWidget(sidebar)
        sidebar.start_new_bean()
        assert sidebar._ref_id_edit.isVisible()
        assert not sidebar._ref_id_display.isVisible()
