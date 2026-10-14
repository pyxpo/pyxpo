"""Showcase of every pyxpo component: inputs, pickers, buttons, selection controls, feedback, cards, tab bar."""
import datetime

from pyxpo import (Alert, AppButton, Avatar, Badge, Card, Checkbox, Chip, DatePicker, Dropdown, Icon, InputField,
                   LabeledCheckbox, ListItem, MultiSelect, NumberInput, PasswordInput, ProgressBar, Radio,
                   RadioGroup, SafeArea, ScrollView, SearchInput, Slider, Stepper, Switch, TabBar, Text, TextArea,
                   ThemeProvider, TimePicker, Typography, View, component, run_app, use_state, Drawer, Stack, Tabs, TopTabs,
                   dark_theme, light_theme)

COL = {"flex": 1}
ROW = {"flex_direction": "row", "gap": 12, "margin_bottom": 14}


def Row(*kids, **kw):
    return View(*kids, style=[ROW, kw.get("style")])


@component
def Components(dark=False, set_dark=None):
    name, set_name = use_state("")
    email, set_email = use_state("")
    pwd, set_pwd = use_state("")
    q, set_q = use_state("")
    choice, set_choice = use_state(None)
    langs, set_langs = use_state(["react", "node"])
    date, set_date = use_state(datetime.date(2026, 10, 14))
    time_, set_time = use_state(datetime.time(9, 41))
    qty, set_qty = use_state(1)
    on, set_on = use_state(True)
    agree, set_agree = use_state(True)
    radio, set_radio = use_state("one")
    vol, set_vol = use_state(0.5)
    msg, set_msg = use_state("")
    step, set_step = use_state(0)
    alert, set_alert = use_state(True)
    return ScrollView(
            Row(View(Typography("UI Components", variant="title"),
                     Typography("All basic components in one place", muted=True), style=COL),
                AppButton(label="Dark" if not dark else "Light", size="sm", variant="outline",
                          on_press=lambda: set_dark(not dark))),
            Row(View(InputField(label="Text Input", left=Icon("user"), placeholder="Enter your name",
                                value=name, on_change_text=set_name), style=COL),
                View(PasswordInput(label="Password Input", placeholder="Password", value=pwd,
                                   on_change_text=set_pwd), style=COL)),
            Row(View(InputField(label="Email Input", left=Icon("mail"), placeholder="you@example.com",
                                value=email, on_change_text=set_email, keyboard_type="email"), style=COL),
                View(SearchInput(label="Search Input", value=q, on_change_text=set_q), style=COL)),
            Row(View(Dropdown(label="Dropdown", options=[{"value": "a", "label": "Option A"},
                                                         {"value": "b", "label": "Option B"},
                                                         {"value": "c", "label": "Option C"}],
                              value=choice, on_change=set_choice), style=COL),
                View(MultiSelect(label="Multi Select", options=[{"value": "react", "label": "React"},
                                                                {"value": "node", "label": "Node.js"},
                                                                {"value": "py", "label": "Python"}],
                                 value=langs, on_change=set_langs), style=COL)),
            Row(View(DatePicker(label="Date Picker", value=date, on_change=set_date), style={"flex": 4}),
                View(TimePicker(label="Time Picker", value=time_, on_change=set_time), style={"flex": 4}),
                View(NumberInput(label="Number Input", value=qty, on_change=set_qty, minimum=0, maximum=99),
                     style={"flex": 3})),
            Typography("Buttons", variant="label", style={"margin_bottom": 6}),
            Row(AppButton(label="Primary", style={"flex": 1}),
                AppButton(label="Secondary", tone="secondary", variant="soft", style={"flex": 1})),
            Row(AppButton(label="Outline", variant="outline", style={"flex": 1}),
                AppButton(label="Danger", tone="danger", variant="soft", style={"flex": 1})),
            Row(View(Typography("Toggle Switch", variant="label", style={"margin_bottom": 6}),
                     Switch(value=on, on_value_change=set_on, track_color={"on": "#1a73e8"})),
                View(Typography("Checkbox", variant="label", style={"margin_bottom": 6}),
                     LabeledCheckbox(value=agree, label="I agree", on_value_change=set_agree)),
                View(Typography("Radio Button", variant="label", style={"margin_bottom": 6}),
                     RadioGroup(options=[{"value": "one", "label": "Option 1"}, {"value": "two", "label": "Option 2"}],
                                value=radio, on_change=set_radio), style=COL)),
            Row(View(Typography("Slider", variant="label", style={"margin_bottom": 6}),
                     View(Slider(value=vol, on_value_change=set_vol, min_track_color="#1a73e8",
                                 style={"flex": 1}),
                          Text("%d%%" % round(vol * 100), style={"margin_left": 10, "width": 44}),
                          style={"flex_direction": "row", "align_items": "center"}), style=COL)),
            Row(View(TextArea(label="Text Area", placeholder="Enter your message...", value=msg,
                              on_change_text=set_msg, lines=3), style={"flex": 1}),
                View(Typography("Stepper", variant="label", style={"margin_bottom": 6}),
                     Stepper(steps=["Details", "Review", "Complete"], current=step),
                     AppButton(label="Next", size="sm", variant="outline",
                               on_press=lambda: set_step((step + 1) % 3), style={"margin_top": 8}),
                     style={"flex": 1})),
            Row(View(Typography("Chip / Tag", variant="label", style={"margin_bottom": 6}),
                     View(Chip("New"), Chip("Popular", tone="success", selected=False),
                          Chip("Sale", tone="danger", selected=False), Chip("Free", tone="neutral", selected=False),
                          style={"flex_direction": "row", "flex_wrap": "wrap", "gap": 8}), style=COL),
                View(Typography("Badge", variant="label", style={"margin_bottom": 6}),
                     View(Badge(label="3", tone="danger"), Badge(label="Inbox", tone="secondary"), Badge(label="12"),
                          style={"flex_direction": "row", "gap": 8}), style=COL)),
            Row(View(Typography("Progress Bar", variant="label", style={"margin_bottom": 10}),
                     ProgressBar(value=0.7), style=COL),
                View(Typography("Alert / Toast", variant="label", style={"margin_bottom": 6}),
                     Alert(title="Success!", message="Your changes have been saved.",
                           on_close=lambda: set_alert(False)) if alert else
                     AppButton(label="Show alert", size="sm", variant="outline", on_press=lambda: set_alert(True)),
                     style=COL)),
            Row(View(Typography("Card", variant="label", style={"margin_bottom": 6}),
                     Card(Typography("Card Title", variant="subheading"),
                          Typography("This is a short description of the card component.", muted=True,
                                     variant="caption"), elevated=False), style=COL),
                View(Typography("Avatar", variant="label", style={"margin_bottom": 6}),
                     Card(ListItem(title="John Doe", subtitle="john@example.com",
                                   left=Avatar(name="John Doe", size=40), right=Icon("chevron-right", size=22),
                                   style={"padding": 0}), elevated=False, style={"padding": 10}), style=COL)),
            style={"flex": 1}, content_container_style={"padding": 16})

def Centered(text, sub=""):
    return View(Typography(text, variant="title"), Typography(sub, muted=True) if sub else None,
                style={"flex": 1, "align_items": "center", "justify_content": "center", "gap": 8})


def PostList(navigation, params):
    return ScrollView(
        *[ListItem(title="Post %d" % i, subtitle="Tap to open", left=Avatar(name="P%d" % i, size=40),
                   right=Icon("chevron-right", size=22), key=str(i), on_press=lambda i=i: navigation.navigate("Post", id=i))
          for i in range(1, 9)], style={"flex": 1})


def PostDetail(navigation, params):
    return View(Centered("Post %s" % params.get("id")),
                AppButton(label="Open drawer", variant="outline", on_press=navigation.open_drawer,
                          style={"margin": 16}),
                style={"flex": 1})


def HomeStack(navigation, params):
    return Stack(screens={"Posts": PostList, "Post": PostDetail}, screen_options={"Post": {"title": "Details"}})


def BottomTabsDemo(navigation, params):
    return Tabs(screens={"Home": HomeStack, "Explore": lambda navigation, params: Centered("Explore"),
                         "Alerts": lambda navigation, params: Centered("Alerts"),
                         "Profile": lambda navigation, params: Centered("Profile")},
                screen_options={"Home": {"icon": "home"}, "Explore": {"icon": "grid"},
                                "Alerts": {"icon": "bell", "badge": True}, "Profile": {"icon": "user"}})


def TopTabsDemo(navigation, params):
    return TopTabs(screens={n: (lambda navigation, params, n=n: Centered(n)) for n in
                            ["Feed", "Popular", "Latest", "Following", "Saved", "Archive"]})


@component
def App():
    dark, set_dark = use_state(False)
    return ThemeProvider(
        SafeArea(
            Drawer(screens={"Components": lambda navigation, params: Components(dark=dark, set_dark=set_dark),
                            "Bottom tabs": BottomTabsDemo, "Top tabs": TopTabsDemo},
                   screen_options={"Components": {"icon": "layers"}, "Bottom tabs": {"icon": "home"},
                                   "Top tabs": {"icon": "compass"}}, drawer_title="pyxpo"),
            edges=("top",), style={"flex": 1, "background_color": (dark_theme if dark else light_theme)["colors"]["background"]}),
        theme=dark_theme if dark else light_theme)


if __name__ == "__main__":
    run_app(App)
