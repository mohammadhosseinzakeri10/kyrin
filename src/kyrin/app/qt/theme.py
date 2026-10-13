"""Dark desktop-control theme for the KYRIN Qt window."""

CONTROL_WINDOW_STYLE = """
QWidget#ControlWindow, QWidget#Content { background: #080b18; color: #e9eeff; }
QFrame#Sidebar { background: #0d1225; border-right: 1px solid #222b48; }
QLabel { color: #c0cbe9; font-size: 14px; }
QLabel#Brand { color: #d7c9ff; font-size: 26px; font-weight: 800; letter-spacing: 3px; }
QLabel#Subtitle { color: #8194bb; font-size: 10px; letter-spacing: 2px; }
QLabel#Welcome { color: #f6f2ff; font-family: 'Lato'; font-size: 47px;
                 font-weight: 900; letter-spacing: 2px; }
QLabel#WelcomeCaption { color: #e4e9ff; font-family: 'Lato'; font-size: 19px;
                        font-weight: 500; letter-spacing: 1px; }
QLabel#SceneHint { color: #a9bcef; font-family: 'Lato'; font-size: 13px;
                   font-weight: 600; letter-spacing: 2px; }
QLabel#PageTitle { color: #eff1ff; font-size: 28px; font-weight: 700; }
QLabel#Status { color: #89e8d4; padding: 8px 12px; background: #132437;
                border: 1px solid #244e5c; border-radius: 10px; }
QLabel#Feedback { color: #d7dbfa; padding: 12px 15px; background: #161c35;
                  border: 1px solid #29345a; border-radius: 10px; }
QLabel#Info { color: #aebae0; margin-top: 18px; }
QLabel#CosmicDashboard { background: #080c1b; border: 1px solid #283050; }
QWidget#HeroCopy { background: transparent; }
QPushButton { background: #27305a; color: #f2f4ff; border: 1px solid #435389;
              border-radius: 9px; padding: 10px 15px; font-weight: 600; }
QPushButton:hover { background: #364479; border-color: #847cff; }
QPushButton:disabled { color: #7883a4; background: #1b2137; border-color: #333b56; }
QPushButton#TtsUtilityButton { color: #f7f8ff; background: #303d70;
                               border: 1px solid #7787be; font-size: 13px;
                               font-weight: 700; padding: 3px 10px; }
QPushButton#TtsUtilityButton:hover { background: #44558e; border-color: #a39dff; }
QPushButton#NavButton { text-align: left; background: transparent; border: 0;
                        color: #aab8de; padding: 13px 15px; }
QPushButton#NavButton:hover { background: #1c2545; }
QPushButton#NavButton:checked { background: #293666; color: #f7f3ff;
                                border-left: 3px solid #a389ff; }
QComboBox, QLineEdit { background: #151d35; color: #f2f4ff;
                       border: 1px solid #3b496f; border-radius: 7px;
                       min-height: 34px; padding: 3px 8px; }
QComboBox QAbstractItemView { background: #18213d; color: #f2f4ff; }
QTabWidget::pane { background: #111a31; border: 1px solid #3b496f;
                   border-radius: 8px; }
QTabBar::tab { background: #1b2746; color: #b9c8eb;
               border: 1px solid #3b496f; border-bottom: 0;
               padding: 9px 16px; margin-right: 4px; }
QTabBar::tab:selected { background: #344b84; color: #ffffff;
                        border-color: #9275ff; }
QTabBar::tab:hover:!selected { background: #293960; }
QCheckBox { color: #e2e9ff; spacing: 10px; padding: 7px 2px; }
QListWidget { background: #111a31; color: #e7edff;
              border: 1px solid #3b496f; border-radius: 8px;
              font-size: 13px; padding: 5px; }
QListWidget::item { padding: 5px 8px; border-radius: 5px; }
QListWidget::item:hover { background: #24345a; }
QListWidget::item:selected { background: #344b84; color: #ffffff; }
QListWidget::indicator { width: 15px; height: 15px; border-radius: 3px; }
QListWidget::indicator:unchecked { background: #1b2a49; border: 1px solid #7890bf; }
QListWidget::indicator:checked { background: #8d73ff; border: 1px solid #d6caff; }
"""
