from pathlib import Path

from beans_stalk.config import DEFAULT_PALETTE, StalkConfig


class TestStalkConfig:
    def test_load_defaults_when_no_file(self, tmp_path):
        config = StalkConfig.load(tmp_path)
        assert config.fade_minutes == 5
        assert config.poll_interval_seconds == 2
        assert config.colors == {}

    def test_load_from_existing_file(self, tmp_path):
        toml_path = tmp_path / "beans-stalk.toml"
        toml_path.write_text(
            'fade_minutes = 10\npoll_interval_seconds = 3\n\n[colors]\nalice = "#ff0000"\n'
        )
        config = StalkConfig.load(tmp_path)
        assert config.fade_minutes == 10
        assert config.poll_interval_seconds == 3
        assert config.colors == {"alice": "#ff0000"}

    def test_save_creates_file(self, tmp_path):
        config = StalkConfig(
            fade_minutes=5, poll_interval_seconds=2, colors={"bob": "#00ff00"}
        )
        config.save(tmp_path)
        assert (tmp_path / "beans-stalk.toml").exists()
        reloaded = StalkConfig.load(tmp_path)
        assert reloaded.colors == {"bob": "#00ff00"}

    def test_get_color_returns_assigned(self, tmp_path):
        config = StalkConfig(colors={"alice": "#ff0000"})
        assert config.get_color("alice") == "#ff0000"

    def test_get_color_auto_assigns_from_palette(self, tmp_path):
        config = StalkConfig(colors={})
        color = config.get_color("alice")
        assert color == DEFAULT_PALETTE[0]
        assert config.colors["alice"] == DEFAULT_PALETTE[0]

    def test_get_color_skips_used_palette_colors(self, tmp_path):
        config = StalkConfig(colors={"alice": DEFAULT_PALETTE[0]})
        color = config.get_color("bob")
        assert color == DEFAULT_PALETTE[1]
        assert config.colors["bob"] == DEFAULT_PALETTE[1]

    def test_get_color_falls_back_to_hash_when_palette_exhausted(self, tmp_path):
        colors = {f"user{i}": c for i, c in enumerate(DEFAULT_PALETTE)}
        config = StalkConfig(colors=colors)
        color = config.get_color("newuser")
        assert color.startswith("#")
        assert len(color) == 7

    def test_layout_algorithm_default(self, tmp_path):
        config = StalkConfig.load(tmp_path)
        assert config.layout_algorithm == "sugiyama"

    def test_layout_algorithm_load(self, tmp_path):
        toml_path = tmp_path / "beans-stalk.toml"
        toml_path.write_text('layout_algorithm = "graphviz_dot"\n')
        config = StalkConfig.load(tmp_path)
        assert config.layout_algorithm == "graphviz_dot"

    def test_layout_algorithm_save_roundtrip(self, tmp_path):
        config = StalkConfig(layout_algorithm="sugiyama_compact")
        config.save(tmp_path)
        reloaded = StalkConfig.load(tmp_path)
        assert reloaded.layout_algorithm == "sugiyama_compact"

    def test_viewports_default_empty(self, tmp_path):
        config = StalkConfig.load(tmp_path)
        assert config.viewports == {}

    def test_viewports_save_roundtrip(self, tmp_path):
        config = StalkConfig(viewports={
            "root": {"center_x": 100.0, "center_y": -50.0, "scale": 1.5},
            "bean-abc": {"center_x": 0.0, "center_y": 0.0, "scale": 0.8},
        })
        config.save(tmp_path)
        reloaded = StalkConfig.load(tmp_path)
        assert reloaded.viewports["root"]["center_x"] == 100.0
        assert reloaded.viewports["root"]["scale"] == 1.5
        assert reloaded.viewports["bean-abc"]["scale"] == 0.8

    def test_layout_direction_default(self, tmp_path):
        config = StalkConfig()
        assert config.layout_direction == "TB"

    def test_layout_direction_persists(self, tmp_path):
        beans_dir = tmp_path / ".beans"
        beans_dir.mkdir()
        config = StalkConfig(layout_direction="LR")
        config.save(beans_dir)
        loaded = StalkConfig.load(beans_dir)
        assert loaded.layout_direction == "LR"

    def test_get_color_for_none_assignee(self):
        config = StalkConfig(colors={})
        color = config.get_color(None)
        assert color.startswith("#")
