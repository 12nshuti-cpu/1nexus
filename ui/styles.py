DARK_THEME = """

/* ============================================================
   GLOBAL
   ============================================================ */

QMainWindow {
    background: qlineargradient(
        spread:pad,
        x1:0,
        y1:0,
        x2:1,
        y2:1,
        stop:0 #020b14,
        stop:0.5 #041520,
        stop:1 #020b14
    );
    border: none;
}

QWidget {
    color: #dce9f5;
    font-family: "Segoe UI";
    font-size: 9.75pt;
}

QToolTip {
    background-color: #081522;
    color: #dce9f5;
    border: 1px solid #1a526c;
    padding: 6px 9px;
}

QScrollArea {
    background-color: transparent;
    border: none;
}

QScrollArea > QWidget > QWidget {
    background-color: transparent;
}

QScrollBar:vertical {
    background-color: #050d16;
    width: 6px;
    margin: 2px;
}

QScrollBar::handle:vertical {
    background-color: #17384c;
    border-radius: 3px;
    min-height: 30px;
}

QScrollBar::handle:vertical:hover {
    background-color: #21627e;
}

QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical {
    height: 0px;
}

QScrollBar:horizontal {
    background-color: #050d16;
    height: 6px;
}

QScrollBar::handle:horizontal {
    background-color: #17384c;
    border-radius: 3px;
}

QScrollBar::add-line:horizontal,
QScrollBar::sub-line:horizontal {
    width: 0px;
}

QFrame#sidebar {
    background: qlineargradient(
        spread:pad,
        x1:0,
        y1:0,
        x2:1,
        y2:1,
        stop:0 #061221,
        stop:1 #030d17
    );
    border: 1px solid #12364e;
    border-left: none;
    border-top: none;
    border-bottom: none;
    border-radius: 0px;
}

QLabel#logo {
    color: #45d9ff;
    font-size: 22px;
    font-weight: 700;
    letter-spacing: 2px;
}

QLabel#subtitle {
    color: #4f7187;
    font-size: 8px;
    font-weight: bold;
    letter-spacing: 1.4px;
}

QLabel#sectionTitle {
    color: #42667c;
    font-size: 9px;
    font-weight: bold;
    letter-spacing: 1.5px;
}

QPushButton#sidebarToggle {
    background-color: #081725;
    border: 1px solid #17374b;
    border-radius: 7px;
    color: #64869b;
    font-size: 16px;
    font-weight: bold;
}

QPushButton#sidebarToggle:hover {
    background-color: #0b2030;
    border: 1px solid #2380a1;
    color: #45d9ff;
}

QPushButton#sidebarToggle:pressed {
    background-color: #0d2b3e;
}

QPushButton#navButton {
    background-color: transparent;
    border: 1px solid transparent;
    border-radius: 8px;
    padding: 10px 12px;
    min-height: 38px;
    text-align: left;
    color: #7b9bb3;
    font-size: 12px;
    font-weight: 600;
}

QPushButton#navButton:hover {
    background-color: #091d2d;
    border: 1px solid #123c55;
    color: #dce9f5;
}

QPushButton#activeButton {
    background: qlineargradient(
        spread:pad,
        x1:0,
        y1:0,
        x2:1,
        y2:0,
        stop:0 rgba(14, 42, 61, 255),
        stop:1 rgba(9, 31, 44, 255)
    );
    border: 1px solid #1d5878;
    border-left: 3px solid #45d9ff;
    border-radius: 8px;
    padding: 10px 12px;
    min-height: 38px;
    text-align: left;
    color: #45d9ff;
    font-size: 12px;
    font-weight: bold;
}

QPushButton#activeButton:hover {
    background-color: #0d3046;
    color: #70e5ff;
}

QPushButton#newConversationButton {
    background-color: #092337;
    border: 1px solid #18506a;
    border-radius: 7px;
    padding: 9px 11px;
    color: #45d9ff;
    text-align: left;
    font-size: 12px;
    font-weight: bold;
}

QPushButton#newConversationButton:hover {
    background-color: #0d3047;
    border: 1px solid #2380a1;
    color: #70e5ff;
}

QPushButton#newConversationButton:pressed {
    background-color: #0b2638;
}

QListWidget#conversationList {
    background-color: transparent;
    border: none;
    outline: none;
    padding: 3px;
    color: #607d91;
}

QListWidget#conversationList::item {
    background-color: transparent;
    border: 1px solid transparent;
    border-radius: 6px;
    padding: 8px;
    margin: 1px 0;
}

QListWidget#conversationList::item:hover {
    background-color: #091b2a;
    border: 1px solid #12354a;
    color: #dce9f5;
}

QListWidget#conversationList::item:selected {
    background-color: #0a2537;
    border: 1px solid #154d66;
    color: #45d9ff;
}

QFrame#dashboardPanel {
    background-color: #071521;
    border: 1px solid #123247;
    border-radius: 9px;
}

QFrame#card {
    background: qlineargradient(
        spread:pad,
        x1:0,
        y1:0,
        x2:0,
        y2:1,
        stop:0 #0a1d2d,
        stop:1 #071722
    );
    border: 1px solid #12354a;
    border-radius: 10px;
}

QFrame#card:hover {
    border: 1px solid #19516a;
}

QFrame#corePanel {
    background-color: #050f1a;
    border: 1px solid #16465e;
    border-radius: 10px;
}

QLabel#pageTitle {
    color: #e8f6ff;
    font-size: 21px;
    font-weight: bold;
    letter-spacing: 1px;
}

QLabel#brandTitle {
    color: #45d9ff;
    font-size: 21pt;
    font-weight: 700;
    letter-spacing: 2px;
}

QLabel#brandSubtitle {
    color: #6c90a4;
    font-size: 9px;
    letter-spacing: 1.8px;
}

QLabel#dateLabel {
    color: #90abc0;
    font-size: 12px;
    letter-spacing: 0.5px;
}

QLabel#clockLabel {
    color: #e8f6ff;
    font-size: 21pt;
    font-weight: 600;
    letter-spacing: 1px;
}

QLabel#topIcon {
    color: #7bb6d9;
    font-size: 16px;
    padding: 8px 10px;
    border: 1px solid #123b54;
    border-radius: 8px;
    background-color: #081b2a;
}

QLabel#statusBadge {
    color: #3ee58b;
    font-size: 11px;
    font-weight: bold;
    padding: 8px 10px;
    border: 1px solid #164b62;
    border-radius: 8px;
    background-color: #071a2a;
}

QLabel#cardTitle {
    color: #52758a;
    font-size: 9px;
    font-weight: bold;
    letter-spacing: 1.5px;
}

QLabel#cardValue {
    color: #e8f6ff;
    font-size: 22px;
    font-weight: bold;
}

QLabel#smallValue {
    color: #45d9ff;
    font-size: 12px;
    font-weight: bold;
}

QLabel#cyanText {
    color: #45d9ff;
    font-weight: bold;
}

QLabel#mutedText {
    color: #527086;
    font-size: 10px;
}

QLabel#online {
    color: #3ee58b;
    font-size: 10px;
    font-weight: bold;
}

QLabel#coreTitle {
    color: #45d9ff;
    font-size: 27px;
    font-weight: bold;
    letter-spacing: 6px;
}

QLabel#coreSubtitle {
    color: #53758c;
    font-size: 9px;
    letter-spacing: 2px;
}

QLabel#coreStatus {
    color: #3ee58b;
    font-size: 9px;
    font-weight: bold;
    letter-spacing: 1px;
}

QFrame#askPanel {
    background-color: #06121e;
    border: 1px solid #16445b;
    border-radius: 9px;
}

QLabel#askIcon {
    color: #45d9ff;
    font-size: 20px;
    font-weight: bold;
}

QLabel#shortcutHint {
    color: #3f6075;
    font-size: 9px;
}

QPlainTextEdit#dashboardInput {
    background-color: transparent;
    border: none;
    padding: 8px 4px;
    color: #e8f6ff;
    font-family: "Consolas";
    font-size: 9.75pt;
}

QLineEdit#searchInput {
    background-color: rgba(10, 27, 39, 180);
    border: 1px solid #174763;
    border-radius: 8px;
    color: #cfe8f6;
    padding: 8px 12px;
    selection-background-color: #174763;
}

QPlainTextEdit#dashboardInput:focus {
    border: none;
}

QPlainTextEdit#assistantInput {
    background-color: #06111c;
    border: 1px solid #16415b;
    border-radius: 8px;
    padding: 11px;
    color: #e6f5ff;
    font-family: "Consolas";
    font-size: 9.75pt;
}

QPlainTextEdit#assistantInput:focus {
    border: 1px solid #25b9e5;
    background-color: #071522;
}

QTextEdit#assistantOutput {
    background-color: #06111b;
    border: 1px solid #123047;
    border-radius: 8px;
    padding: 14px;
    color: #c9d9e5;
    font-size: 9.75pt;
    selection-background-color: #16445b;
    selection-color: #e8f6ff;
}

QTextEdit#assistantOutput p {
    margin-top: 5px;
    margin-bottom: 8px;
}

QTextEdit#assistantOutput code {
    background-color: #0c1c2a;
    color: #72dfff;
}

QTextEdit#assistantOutput pre {
    background-color: #081722;
    border: 1px solid #183b50;
    border-radius: 6px;
    padding: 10px;
    color: #cce8f4;
}

QTextEdit#assistantOutput a {
    color: #45d9ff;
}

QTextEdit {
    background-color: #07121d;
    border: 1px solid #123047;
    border-radius: 7px;
    padding: 10px;
    color: #c9d9e5;
    selection-background-color: #16445b;
}

QTextEdit:focus {
    border: 1px solid #1c5d77;
}

QTextEdit p {
    margin: 5px 0;
}

QTextEdit code {
    background-color: #0c1b29;
}

QTextEdit pre {
    background-color: #0a1825;
    border: 1px solid #18384d;
    border-radius: 5px;
    padding: 9px;
}

QPlainTextEdit {
    background-color: #07121d;
    border: 1px solid #123047;
    border-radius: 7px;
    padding: 10px;
    color: #c9d9e5;
    font-family: "Consolas";
    font-size: 12px;
    selection-background-color: #16445b;
}

QPlainTextEdit:focus {
    border: 1px solid #1c5d77;
}

QPushButton#quickCommand {
    background-color: #081a28;
    border: 1px solid #14384d;
    border-radius: 6px;
    padding: 8px;
    color: #6b8da1;
    text-align: left;
    font-size: 11px;
}

QPushButton#quickCommand:hover {
    background-color: #0c293d;
    border: 1px solid #1e6684;
    color: #45d9ff;
}

QPushButton#quickCommand:pressed {
    background-color: #0d3147;
}

QLabel#timelineText {
    color: #6d8ca0;
    font-family: "Consolas";
    font-size: 10px;
}

QPlainTextEdit#systemOutput {
    background-color: #06111b;
    border: 1px solid #102f43;
    color: #7fa1b5;
    font-family: "Consolas";
    font-size: 11px;
}

QTextEdit#activityOutput {
    background-color: #06111b;
    border: 1px solid #123047;
    border-radius: 8px;
    padding: 14px;
    color: #b9d0dd;
    font-family: "Consolas";
    font-size: 12px;
}

QTextEdit#activityOutput p {
    margin-top: 4px;
    margin-bottom: 8px;
}

QPushButton {
    outline: none;
}

QPushButton:disabled {
    color: #314957;
    border-color: #0d202c;
}

QPlainTextEdit::selection {
    background-color: #16445b;
    color: #e8f6ff;
}

QTextEdit::selection {
    background-color: #16445b;
    color: #e8f6ff;
}

QLineEdit:focus {
    border: 1px solid #25b9e5;
}

QListWidget:focus {
    border: none;
}

QPushButton:focus {
    outline: none;
}

QMenu {
    background-color: #081722;
    border: 1px solid #16415b;
    padding: 5px;
    color: #c9d9e5;
}

QMenu::item {
    background-color: transparent;
    padding: 8px 22px;
    border-radius: 5px;
}

QMenu::item:selected {
    background-color: #0d293d;
    color: #45d9ff;
}

QMenu::separator {
    height: 1px;
    background-color: #123047;
    margin: 5px 8px;
}

QMessageBox {
    background-color: #07121d;
}

QMessageBox QLabel {
    color: #dce9f5;
}

QMessageBox QPushButton {
    background-color: #092337;
    border: 1px solid #18506a;
    border-radius: 6px;
    padding: 7px 18px;
    color: #45d9ff;
    min-width: 70px;
}

QMessageBox QPushButton:hover {
    background-color: #0d3047;
    border: 1px solid #2380a1;
}

QInputDialog {
    background-color: #07121d;
}

QInputDialog QLabel {
    color: #c9d9e5;
}

QInputDialog QLineEdit {
    background-color: #06111c;
    border: 1px solid #16415b;
    border-radius: 6px;
    padding: 8px;
    color: #e8f6ff;
}

QInputDialog QPushButton {
    background-color: #092337;
    border: 1px solid #18506a;
    border-radius: 6px;
    padding: 7px 16px;
    color: #45d9ff;
}

QInputDialog QPushButton:hover {
    background-color: #0d3047;
}

QFrame#corePanel {
    background: qlineargradient(
        spread:pad,
        x1:0,
        y1:0,
        x2:1,
        y2:1,
        stop:0 #061523,
        stop:1 #040e18
    );
    border: 1px solid #1a5976;
    border-radius: 16px;
}

QFrame#corePanel:hover {
    border: 1px solid #1c6986;
}

QFrame#topBar {
    background: qlineargradient(
        spread:pad,
        x1:0,
        y1:0,
        x2:1,
        y2:0,
        stop:0 #091c2d,
        stop:1 #071722
    );
    border: 1px solid #123b52;
    border-radius: 12px;
}

QFrame#heroPanel {
    background: qlineargradient(
        spread:pad,
        x1:0,
        y1:0,
        x2:1,
        y2:1,
        stop:0 #071b2b,
        stop:1 #050f1c
    );
    border: 1px solid #184b66;
    border-radius: 18px;
    min-height: 260px;
}

QLabel#heroTitle {
    color: #dfeefc;
    font-size: 17px;
    font-weight: 600;
    letter-spacing: 0.5px;
}

QLabel#heroText {
    color: #8aa7bb;
    font-size: 9.75pt;
}

QLabel#orbLabel {
    color: #45d9ff;
    font-size: 21pt;
    font-weight: 700;
    letter-spacing: 10px;
    padding: 16px;
    border: 2px solid #2ec9ff;
    border-radius: 50%;
    background: qradialgradient(
        cx:0.5,
        cy:0.5,
        radius:0.8,
        fx:0.5,
        fy:0.5,
        stop:0 rgba(53, 202, 255, 140),
        stop:0.35 rgba(22, 110, 180, 80),
        stop:1 rgba(10, 20, 35, 30)
    );
    min-width: 240px;
    min-height: 160px;
}

QLabel#orbSub {
    color: #45d9ff;
    font-size: 12px;
    letter-spacing: 4px;
}

QLabel#systemOnline {
    color: #3ee58b;
    font-size: 10px;
    font-weight: bold;
}

QLabel#systemWarning {
    color: #e5c85c;
    font-size: 10px;
    font-weight: bold;
}

QLabel#systemError {
    color: #e76b78;
    font-size: 10px;
    font-weight: bold;
}

QLabel#dashboardClock {
    color: #45d9ff;
    font-family: "Consolas";
    font-size: 15px;
    font-weight: bold;
}

QLabel#dashboardSystem {
    color: #3ee58b;
    font-size: 9px;
    font-weight: bold;
    letter-spacing: 1px;
}

QWidget#systemGraph {
    background-color: #071522;
    border: none;
}

QFrame#meterPanel {
    background-color: #071522;
    border: 1px solid #123247;
    border-radius: 9px;
}

QFrame#meterPanel:hover {
    border: 1px solid #18516a;
}

QLabel#telemetryLabel {
    color: #52758a;
    font-size: 9px;
    font-weight: bold;
    letter-spacing: 1px;
}

QLabel#telemetryValue {
    color: #e8f6ff;
    font-family: "Consolas";
    font-size: 15px;
    font-weight: bold;
}

QFrame#activityPanel {
    background: qlineargradient(
        spread:pad,
        x1:0,
        y1:0,
        x2:1,
        y2:1,
        stop:0 #061722,
        stop:1 #050f1a
    );
    border: 1px solid #123047;
    border-radius: 12px;
}

QLabel#activityTitle {
    color: #b9d0dd;
    font-size: 11px;
    font-weight: bold;
    letter-spacing: 1.5px;
}

QLabel#activityEntry {
    color: #dfeefc;
    font-size: 11px;
}

QLabel#activityTime {
    color: #6d8ea3;
    font-size: 10px;
}

QLabel#activityDot {
    color: #45d9ff;
    font-size: 10px;
}

QFrame#missionPanel {
    background-color: #071522;
    border: 1px solid #123247;
    border-radius: 9px;
}

QLabel#missionTitle {
    color: #45d9ff;
    font-size: 10px;
    font-weight: bold;
    letter-spacing: 1px;
}

QFrame#commandPanel {
    background-color: #06111c;
    border: 1px solid #16415b;
    border-radius: 9px;
}

QLabel#commandLabel {
    color: #52758a;
    font-size: 9px;
    font-weight: bold;
    letter-spacing: 1px;
}

QLabel#status {
    color: #3ee58b;
    font-weight: bold;
}

QLabel#statusOffline {
    color: #e76b78;
    font-weight: bold;
}

QLabel#statusBusy {
    color: #e5c85c;
    font-weight: bold;
}

QFrame#assistantHeader {
    background-color: #071521;
    border: 1px solid #123247;
    border-radius: 9px;
}

QLabel#assistantTitle {
    color: #e8f6ff;
    font-size: 21px;
    font-weight: bold;
}

QLabel#assistantSubtitle {
    color: #527086;
    font-size: 10px;
}

QFrame#activityHeader,
QFrame#systemHeader {
    background-color: #071521;
    border: 1px solid #123247;
    border-radius: 9px;
}

QLabel#statusDot {
    color: #3ee58b;
    font-size: 12px;
}

QLabel#cyanDot {
    color: #45d9ff;
    font-size: 12px;
}

QLabel#purpleDot {
    color: #8c7cff;
    font-size: 12px;
}

QLabel#brand {
    color: #45d9ff;
    font-size: 11px;
    font-weight: bold;
    letter-spacing: 2px;
}

QLabel#brandSecondary {
    color: #527086;
    font-size: 8px;
    letter-spacing: 1px;
}

QPlainTextEdit#commandInput {
    background-color: #06111c;
    border: 1px solid #16415b;
    border-radius: 8px;
    padding: 10px;
    color: #e6f5ff;
    font-family: "Consolas";
    font-size: 9.75pt;
}

QPlainTextEdit#commandInput:hover {
    border: 1px solid #1b5872;
}

QPlainTextEdit#commandInput:focus {
    border: 1px solid #25b9e5;
}

QPushButton#primaryButton {
    background-color: #092337;
    border: 1px solid #18506a;
    border-radius: 7px;
    padding: 8px 14px;
    color: #45d9ff;
    font-weight: bold;
}

QPushButton#primaryButton:hover {
    background-color: #0d3047;
    border: 1px solid #2380a1;
}

QPushButton#primaryButton:pressed {
    background-color: #0b2638;
}

QPushButton#secondaryButton {
    background-color: #081722;
    border: 1px solid #14384d;
    border-radius: 7px;
    padding: 8px 14px;
    color: #6b8da1;
}

QPushButton#secondaryButton:hover {
    background-color: #0c293c;
    border: 1px solid #1e6684;
    color: #dce9f5;
}

QPushButton#dangerButton {
    background-color: #24131a;
    border: 1px solid #51232d;
    border-radius: 6px;
    padding: 7px 12px;
    color: #e77a86;
}

QPushButton#dangerButton:hover {
    background-color: #321820;
    border: 1px solid #78333e;
    color: #ff9aa4;
}

QPlainTextEdit:disabled {
    background-color: #050d15;
    color: #3d5665;
    border-color: #0d202c;
}

QTextEdit table {
    background-color: #081722;
    border: 1px solid #1a4e69;
    width: 100%;
}

QTextEdit th {
    background-color: #0d2434;
    color: #45d9ff;
    font-weight: bold;
    padding: 8px 10px;
    border: 1px solid #1d5875;
}

QTextEdit td {
    color: #d9eaf4;
    padding: 8px 10px;
    border: 1px solid #183c4d;
    background-color: rgba(9, 21, 30, 180);
}

QTextEdit tr:nth-child(even) td {
    background-color: rgba(13, 30, 42, 180);
}

QTextEdit pre {
    background-color: #071522;
    border: 1px solid #183b50;
    border-radius: 6px;
    padding: 10px;
    color: #bfe5f1;
    font-family: "Consolas";
}

QTextEdit code {
    color: #72dfff;
    font-family: "Consolas";
}

QFrame#separator {
    background-color: #123047;
    max-height: 1px;
}

QStatusBar {
    background-color: #050d16;
    border-top: 1px solid #10293a;
    color: #527086;
}

QStatusBar QLabel {
    color: #527086;
    font-size: 9px;
}

QWidget#centralWidget {
    background-color: #040a12;
}

QFrame#coreOverview {
    background-color: rgba(4, 18, 29, 190);
    border: 1px solid #123b52;
    border-radius: 8px;
    min-width: 145px;
}

QFrame#telemetryMini {
    background-color: rgba(8, 30, 43, 210);
    border: 1px solid #123449;
    border-left: 2px solid #45d9ff;
    border-radius: 5px;
}

QLabel#microTitle {
    color: #5e859a;
    font-size: 8px;
    font-weight: bold;
    letter-spacing: 1.2px;
}

QLabel#telemetryCyan,
QLabel#telemetryPurple,
QLabel#telemetryGreen,
QLabel#telemetryYellow {
    font-size: 10px;
    font-weight: bold;
}

QLabel#telemetryCyan { color: #54dcff; }
QLabel#telemetryPurple { color: #ae91ff; }
QLabel#telemetryGreen { color: #52dc9b; }
QLabel#telemetryYellow { color: #e5ca70; }

QPushButton#agentCard {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #0a2637, stop:1 #071825);
    border: 1px solid #15455e;
    border-radius: 7px;
    color: #b9e4f2;
    font-size: 10px;
    font-weight: bold;
    padding: 7px 8px;
    text-align: left;
}

QPushButton#agentCard:hover {
    background-color: #10354a;
    border: 1px solid #42c9ef;
    color: #75e6ff;
}

QPushButton#agentCard:pressed {
    background-color: #0b2030;
}

QFrame#hudPanel,
QFrame#metricCard {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #071d30, stop:1 #040f1d);
    border: 1px solid #1375a7;
    border-radius: 9px;
}

QFrame#hudPanel:hover,
QFrame#metricCard:hover {
    border-color: #26d2ff;
}

QLabel#hudPanelTitle {
    color: #66dbff;
    font-size: 11px;
    font-weight: bold;
    letter-spacing: 1.2px;
}

QLabel#railCoreName {
    color: #2ed9ff;
    font-size: 15px;
    font-weight: bold;
    padding: 7px 0 2px 0;
}

QFrame#statLine {
    background-color: rgba(5, 21, 34, 180);
    border: 1px solid #103d57;
    border-radius: 5px;
}

QLabel#statLineValue,
QLabel#railStat {
    color: #b5e9ff;
    font-family: "Consolas";
    font-size: 10px;
}

QLabel#railStat {
    background-color: #071b2b;
    border-left: 2px solid #35dbff;
    padding: 9px;
}

QPushButton#actionButton {
    background: #081d2e;
    border: 1px solid #11527a;
    border-radius: 7px;
    color: #aee9ff;
    min-height: 30px;
    padding: 7px 9px;
    text-align: left;
    font-size: 10px;
}

QPushButton#actionButton:hover {
    background: #0c3048;
    border-color: #26d2ff;
    color: #ffffff;
}

QFrame#metricCard {
    min-height: 205px;
}

QLabel#metricDetail {
    color: #78b6d0;
    font-family: "Consolas";
    font-size: 11px;
    font-weight: bold;
}

QFrame#dashboardMetricCard {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #091f31, stop:1 #06121f);
    border: 1px solid #12618c;
    border-radius: 9px;
    min-height: 158px;
}

QFrame#dashboardMetricCard:hover {
    border-color: #31d9ff;
    background-color: #0a2a40;
}

QLabel#metricIcon {
    color: #38d9ff;
    font-size: 15px;
    font-weight: bold;
}

QLabel#metricCardTitle {
    color: #b9e7fb;
    font-size: 10px;
    font-weight: bold;
    letter-spacing: 1px;
}

QLabel#metricFooter {
    color: #4d829a;
    font-size: 8px;
    font-weight: bold;
    letter-spacing: 1px;
}

QScrollArea#dashboardScroll {
    background-color: #030d17;
}

/* ============================================================
   NEXUS UI UPGRADE — COMPATIBILITY LAYER
   Keeps the original palette and selectors above, while styling
   the newer global header, Assistant workspace and live rail.
   ============================================================ */

QFrame#globalHeader {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #061523, stop:0.55 #041520, stop:1 #061523);
    border: 1px solid #123b52;
    border-top: none;
}

QLabel#globalBrandTitle {
    color: #45d9ff;
    font-size: 25px;
    font-weight: 700;
    letter-spacing: 4px;
}

QLabel#globalBrandSubtitle {
    color: #527086;
    font-size: 9px;
    font-weight: 600;
    letter-spacing: 1.6px;
}

/* Larger functional header controls, replacing tiny decorative glyphs. */
QPushButton#headerIconButton,
QPushButton#inputIconButton,
QPushButton#sendIconButton {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #081d2d, stop:1 #06131f);
    border: 1px solid #18506a;
    border-radius: 9px;
    color: #45d9ff;
    font-size: 15px;
    font-weight: 600;
    padding: 0px;
}

QPushButton#headerIconButton {
    min-width: 42px;
    min-height: 42px;
}

QPushButton#headerIconButton:hover,
QPushButton#inputIconButton:hover,
QPushButton#sendIconButton:hover {
    background: #0b2b40;
    border-color: #2acfff;
    color: #72e5ff;
}

QPushButton#headerIconButton:pressed,
QPushButton#inputIconButton:pressed,
QPushButton#sendIconButton:pressed {
    background: #0d3449;
}

QPushButton#headerIconButton:disabled,
QPushButton#inputIconButton:disabled,
QPushButton#sendIconButton:disabled {
    color: #3b5665;
    border-color: #102b3b;
}

QLabel#statusBadge,
QLabel#onlineBadge {
    background-color: #071a2a;
    border: 1px solid #164b62;
    border-radius: 12px;
    color: #3ee58b;
    padding: 7px 10px;
    font-size: 10px;
    font-weight: bold;
}

QLabel#modelBadge {
    background-color: #081b2a;
    border: 1px solid #174f69;
    border-radius: 10px;
    color: #45d9ff;
    padding: 7px 10px;
    font-family: "Consolas";
    font-size: 10px;
    font-weight: bold;
}

QMenu#notificationsMenu {
    background-color: #081722;
    border: 1px solid #1a526c;
    padding: 6px;
}

QMenu#notificationsMenu::item {
    padding: 9px 14px;
    border-radius: 5px;
}

QMenu#notificationsMenu::item:selected {
    background-color: #0d293d;
    color: #45d9ff;
}

/* Sidebar labels/icons from the redesigned navigation widgets. */
QPushButton#navButton,
QPushButton#activeButton {
    min-height: 48px;
    padding: 0px 10px;
    border-radius: 9px;
}

QLabel#navButtonLabel {
    color: #9bc4d8;
    font-size: 13px;
    font-weight: 600;
}

QPushButton#activeButton QLabel#navButtonLabel {
    color: #e8faff;
}

/* Conversation list rows are real widgets; keep them visually consistent
   with the original QListWidget selection language. */
QFrame#conversationRow {
    background-color: transparent;
    border: 1px solid transparent;
    border-radius: 8px;
}

QLabel#conversationRowTitle {
    color: #abd3e7;
    font-size: 11px;
    font-weight: 600;
}

QLabel#conversationRowStamp {
    color: #567f95;
    font-size: 9px;
}

/* Assistant page: reference-style two-column workspace. */
QFrame#assistantHeader {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #071b2b, stop:1 #050f1c);
    border: 1px solid #16465e;
    border-radius: 10px;
}

QFrame#assistantWorkspace {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #061724, stop:1 #040e18);
    border: 1px solid #16465e;
    border-radius: 11px;
}

QFrame#assistantWorkspace:hover {
    border-color: #1d6988;
}

QLabel#hudPanelTitle {
    color: #45d9ff;
    font-size: 11px;
    font-weight: bold;
    letter-spacing: 1.4px;
}

QComboBox#voiceLanguageCombo {
    background-color: #071a28;
    border: 1px solid #16415b;
    border-radius: 7px;
    color: #a9cfe0;
    min-height: 41px;
    padding: 0 10px;
}

QComboBox#voiceLanguageCombo:hover,
QComboBox#voiceLanguageCombo:focus {
    border-color: #25b9e5;
}

QComboBox#voiceLanguageCombo QAbstractItemView {
    background-color: #081722;
    border: 1px solid #16415b;
    color: #c9d9e5;
    selection-background-color: #0d3047;
    selection-color: #45d9ff;
}

QFrame#assistantRail {
    background: transparent;
    border: none;
}

QFrame#hudPanel {
    min-width: 0px;
}

QFrame#statLine {
    min-height: 34px;
}

QLabel#statLineValue {
    color: #d8f4ff;
    font-size: 10px;
    font-weight: bold;
}

QPushButton#actionButton {
    min-height: 41px;
    font-size: 10px;
    padding: 5px 7px;
}

QPushButton#actionButton QLabel#buttonText {
    color: #ccecf8;
    font-size: 10px;
    font-weight: 600;
}

QPushButton#actionButton:hover QLabel#buttonText {
    color: #ffffff;
}

/* The HUD icon widget itself is painted with QPainter, so size/spacing are
   controlled here rather than by fake Unicode characters. */
HudIcon {
    background: transparent;
}

QLabel#shortcutHint {
    color: #4f7389;
    font-size: 9px;
}

/* Stronger visibility for the fixed global header on every page. */
QFrame#globalHeader QLabel {
    background: transparent;
}

QLineEdit#searchInput {
    min-height: 40px;
    border-radius: 20px;
    padding: 0px 15px;
    font-size: 11px;
}

QFrame#globalHeader QLineEdit#searchInput {
    background-color: #06121e;
    border: 1px solid #18506a;
}

QFrame#globalHeader QLineEdit#searchInput:hover,
QFrame#globalHeader QLineEdit#searchInput:focus {
    border-color: #28cfff;
}

/* ============================================================
   RESPONSIVE FIT / ANTI-CLIPPING
   ============================================================ */
QScrollArea#assistantScroll,
QScrollArea#systemScroll,
QScrollArea#activityScroll {
    background: #020b14;
    border: none;
}

QScrollArea#assistantScroll > QWidget > QWidget,
QScrollArea#systemScroll > QWidget > QWidget,
QScrollArea#activityScroll > QWidget > QWidget {
    background: #020b14;
}

#assistantHeader,
#assistantWorkspace,
#assistantRail,
#hudPanel,
#metricCard,
#activityPanel,
#dashboardPanel,
#askPanel {
    min-width: 0px;
}

#assistantOutput,
#assistantInput,
#dashboardInput,
#activityOutput,
#systemOutput {
    min-width: 0px;
    min-height: 0px;
}

#voiceLanguageCombo,
#modelBadge,
#statusBadge,
#onlineBadge {
    max-width: 180px;
}



/* ============================================================
   RESPONSIVE TEXT / NO-OVERFLOW SAFETY
   ============================================================ */

QListWidget#conversationList {
}

QFrame#conversationRow {
    min-width: 0;
    background: transparent;
}

QLabel#conversationRowTitle,
QLabel#conversationRowStamp,
QLabel#statLineValue,
QLabel#railCoreName,
QLabel#mutedText,
QLabel#cardTitle,
QLabel#telemetryLabel,
QLabel#buttonText {
    min-width: 0;
}

QLabel#conversationRowTitle {
    padding: 0;
}

QTextEdit#assistantOutput,
QTextEdit#activityOutput,
QPlainTextEdit#assistantInput,
QPlainTextEdit#dashboardInput,
QPlainTextEdit#commandInput,
QPlainTextEdit#systemOutput {
    min-width: 0;
}


/* The conversation item contains a custom widget; the delegate must not add
   its own padded text area around it. */
QListWidget#conversationList::item {
    padding: 0px;
    margin: 2px 0px;
}

QFrame#conversationRow {
    min-width: 0px;
}

QLabel#conversationRowTitle, QLabel#conversationRowStamp,
QLabel#telemetryLabel, QLabel#statLineValue, QLabel#buttonText {
    min-width: 0px;
}

QTextEdit#assistantOutput {
    min-width: 0px;
    min-height: 0px;
}


/* Text-fit safeguards for custom rows and compact HUD cards. */
QListWidget#conversationList::item {
    padding: 0px;
}
QFrame#conversationRow {
    min-width: 0px;
}
QLabel#conversationRowTitle, QLabel#conversationRowStamp,
QLabel#telemetryLabel, QLabel#statLineValue, QLabel#buttonText {
    min-width: 0px;
}


/* ============================================================
   DASHBOARD REFERENCE UI — POLISHED RESPONSIVE LAYER
   ============================================================ */

QScrollArea#dashboardScroll {
    background: #020b14;
    border: none;
}

QScrollArea#dashboardScroll > QWidget > QWidget {
    background: #020b14;
}

QFrame#heroPanel {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #071a2a, stop:0.45 #061522, stop:1 #04101b);
    border: 1px solid #14658b;
    border-radius: 12px;
    min-height: 260px;
}

QLabel#heroTitle {
    color: #bfe7fb;
    font-size: 17px;
    font-weight: 600;
    letter-spacing: 1px;
}

QLabel#heroDescription {
    color: #75a9c2;
    font-size: 10px;
    line-height: 1.35em;
}

QFrame#coreOverview {
    background: rgba(4, 18, 29, 215);
    border: 1px solid #123f58;
    border-radius: 8px;
}

QFrame#dashboardMetricCard {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #071a29, stop:1 #050f19);
    border: 1px solid #15567a;
    border-radius: 10px;
    min-height: 185px;
}

QFrame#dashboardMetricCard:hover {
    border-color: #2acbff;
    background: #082034;
}

QFrame#dashboardMetricIconBadge,
QFrame#dashboardActivityIconBadge {
    background: #071a2a;
    border: 1px solid #155471;
    border-radius: 19px;
}

QLabel#metricCardTitle {
    color: #b9dff0;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 1px;
}

QFrame#dashboardActivityRow {
    background: transparent;
    border: none;
}

QFrame#dashboardSeparator,
QFrame#dashboardTimelineLine {
    background: #103149;
    max-height: 1px;
}

QLabel#dashboardActivityTitle {
    color: #d7eaf7;
    font-size: 10px;
    font-weight: 600;
}

QLabel#dashboardActivityDetail {
    color: #63879b;
    font-size: 8px;
}

QLabel#dashboardActivityTime {
    color: #62a5c5;
    font-size: 8px;
}

QLabel#dashboardTimelineTime {
    color: #a9c6d5;
    font-family: "Consolas";
    font-size: 8px;
}

QLabel#dashboardTimelineNode {
    color: #21d9ff;
    font-size: 10px;
}

QLabel#dashboardTimelineTitle {
    color: #c9dce8;
    font-size: 9px;
}

QLabel#dashboardTimelineStatus {
    color: #38e4ae;
    font-size: 8px;
    font-weight: 700;
}

QPushButton#dashboardLinkButton {
    background: transparent;
    border: none;
    padding: 1px 2px;
    color: #21cfff;
    font-size: 8px;
    font-weight: 600;
}

QPushButton#dashboardLinkButton:hover {
    color: #76e9ff;
}

QPushButton#dashboardCommandButton {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #071c2c, stop:1 #06131f);
    border: 1px solid #144965;
    border-radius: 8px;
    min-height: 42px;
    padding: 5px 6px;
    text-align: left;
}

QPushButton#dashboardCommandButton:hover {
    background: #0b2a3d;
    border-color: #2acbff;
}

QPushButton#dashboardCommandButton:pressed {
    background: #0d344b;
}

QLabel#buttonText {
    color: #b9d9e8;
    font-size: 9px;
    font-weight: 600;
}

QPushButton#dashboardRecentRow {
    background: #061522;
    border: 1px solid transparent;
    border-radius: 8px;
    min-height: 42px;
    padding: 1px;
    text-align: left;
}

QPushButton#dashboardRecentRow:hover {
    background: #09273a;
    border-color: #175a79;
}

QLabel#dashboardRecentTitle {
    color: #cfe2ed;
    font-size: 9px;
    font-weight: 600;
}

QLabel#dashboardRecentStamp {
    color: #5a7f93;
    font-size: 7px;
}

QPushButton#dashboardMicButton,
QPushButton#dashboardSendButton,
QPushButton#dashboardSettingsButton,
QPushButton#dashboardAssistantButton {
    background: #061c2c;
    border: 1px solid #175a79;
    color: #52dcff;
    padding: 0px;
}

QPushButton#dashboardMicButton {
    border-radius: 22px;
}

QPushButton#dashboardSendButton,
QPushButton#dashboardSettingsButton,
QPushButton#dashboardAssistantButton {
    border-radius: 9px;
}

QPushButton#dashboardMicButton:hover,
QPushButton#dashboardSendButton:hover,
QPushButton#dashboardSettingsButton:hover,
QPushButton#dashboardAssistantButton:hover {
    background: #0b2d42;
    border-color: #2acbff;
}

QPushButton#dashboardMicButton:disabled {
    background: #08263a;
    border-color: #2acbff;
}

QPushButton#dashboardMicButton[listening="true"],
QPushButton#assistantMicButton[listening="true"] {
    background: #0b3340;
    border-color: #34e5be;
}

QPushButton#dashboardVoiceToggle {
    background: #061a29;
    border: 1px solid #16516b;
    border-radius: 21px;
    color: #6f9bb0;
    padding: 0px 11px;
    font-size: 8px;
    font-weight: 700;
    letter-spacing: 1px;
}

QPushButton#dashboardVoiceToggle:checked {
    background: #092b32;
    border-color: #21d9a0;
    color: #59eab4;
}

QPushButton#dashboardVoiceToggle:hover {
    border-color: #2acbff;
    color: #d9f7ff;
}

QFrame#askPanel {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #061522, stop:0.55 #04131f, stop:1 #061522);
    border: 1px solid #155375;
    border-radius: 10px;
}

QPlainTextEdit#dashboardInput {
    background: #04101a;
    border: 1px solid #11394e;
    border-radius: 20px;
    padding: 8px 13px;
    color: #d9effa;
    font-family: "Segoe UI";
    font-size: 9.5pt;
}

QPlainTextEdit#dashboardInput:focus {
    border: 1px solid #2acbff;
}

/* Assistant microphone is deliberately circular and icon-only, so a text glyph
   can never sit under/over the painted microphone. */
QPushButton#inputIconButton,
QPushButton#assistantMicButton {
    border-radius: 10px;
    padding: 0px;
    min-width: 46px;
    max-width: 46px;
    min-height: 46px;
    max-height: 46px;
}

QPushButton#assistantMicButton:hover {
    background: #0b2d42;
    border-color: #2acbff;
}

QPushButton#assistantMicButton:disabled {
    background: #08263a;
    border-color: #34e5be;
}

QPushButton#sendIconButton {
    border-radius: 9px;
    padding: 0px;
}

/* The painted HUD icon is always contained inside its owning button. */
HudIcon {
    min-width: 16px;
    min-height: 16px;
}

/* Never allow generic Qt button padding to create accidental icon overlap. */
QPushButton#headerIconButton,
QPushButton#inputIconButton,
QPushButton#assistantMicButton,
QPushButton#sendIconButton,
QPushButton#dashboardMicButton,
QPushButton#dashboardSendButton,
QPushButton#dashboardSettingsButton,
QPushButton#dashboardAssistantButton {
    padding: 0px;
}



/* ============================================================
   SYSTEM REFERENCE SCREEN — LARGE, LEGIBLE HUD CONTROLS
   ============================================================ */
QFrame#systemReferencePanel {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #061724, stop:0.5 #04131f, stop:1 #030d17);
    border: 1px solid #145b7d;
    border-radius: 11px;
}

QFrame#systemReferencePanel:hover {
    border-color: #1b759d;
}

QLabel#systemReferenceTitle {
    color: #5adfff;
    font-size: 15px;
    font-weight: 700;
    letter-spacing: 1px;
}

QLabel#systemReferenceTitleSmall {
    color: #b7dded;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.8px;
}

QLabel#systemReferenceSubtitle {
    color: #4f8ca7;
    font-size: 8px;
    font-weight: 600;
    letter-spacing: 0.9px;
}

QFrame#systemHeaderIconBadge,
QFrame#systemMetricIconBadge,
QFrame#systemStatIconBadge,
QFrame#systemHardwareIconBadge {
    background: #061c2d;
    border: 1px solid #146487;
    border-radius: 12px;
}

QFrame#systemHeaderIconBadge {
    border-radius: 26px;
}

QFrame#systemMetricIconBadge,
QFrame#systemStatIconBadge,
QFrame#systemHardwareIconBadge {
    border-radius: 21px;
}

QLabel#systemLiveBadge {
    background: #082b2c;
    border: 1px solid #1ecda5;
    border-radius: 17px;
    color: #46edc0;
    padding: 0 10px;
    font-size: 9px;
    font-weight: 700;
}

QLabel#systemMetricTitle {
    color: #b9dff0;
    font-size: 9px;
    font-weight: 700;
    letter-spacing: 0.7px;
}

QLabel#systemMetricDetail {
    color: #61b0cb;
    font-size: 8px;
    font-weight: 600;
}

QLabel#systemLiveStatLabel,
QLabel#systemBarLabel,
QLabel#systemHardwareLabel {
    color: #8fc7dc;
    font-size: 8px;
    font-weight: 600;
}

QLabel#systemLiveStatValue,
QLabel#systemBarValue,
QLabel#systemHardwareValue {
    color: #dff7ff;
    font-size: 9px;
    font-weight: 700;
}

QFrame#systemLiveStatRow {
    background: transparent;
    border: none;
}

QLabel#systemInfoKey {
    color: #24dfff;
    font-family: "Consolas";
    font-size: 8px;
    font-weight: 700;
}

QLabel#systemInfoValue {
    color: #d0ebf6;
    font-family: "Consolas";
    font-size: 8px;
}

QPlainTextEdit#systemLogsOutput {
    background: #04111b;
    border: 1px solid #0d3b52;
    border-radius: 6px;
    color: #a8d9e8;
    padding: 7px 9px;
    font-family: "Consolas";
    font-size: 8px;
}

QPlainTextEdit#systemLogsOutput:focus {
    border-color: #1b789f;
}

QFrame#systemMetricCard {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #071b2b, stop:1 #040e17);
    border: 1px solid #145a7b;
    border-radius: 10px;
}

QFrame#systemMetricCard:hover {
    background: #082238;
    border-color: #29cfff;
}

/* Larger icon drawing is intentional on the System page. */
QFrame#systemMetricCard HudIcon,
QFrame#systemReferencePanel HudIcon {
    min-width: 22px;
    min-height: 22px;
}

QScrollArea#systemScroll {
    background: #020a12;
    border: none;
}

QScrollArea#systemScroll > QWidget > QWidget {
    background: #020a12;
}

QWidget#systemCompactBar,
QWidget#systemReferencePanel QWidget {
    min-width: 0px;
}

QPushButton#assistantMicButton {
    min-width: 46px;
    max-width: 46px;
    min-height: 46px;
    max-height: 46px;
    padding: 0px;
    border-radius: 23px;
}

QPushButton#dashboardMicButton {
    min-width: 48px;
    max-width: 48px;
    min-height: 48px;
    max-height: 48px;
    padding: 0px;
    border-radius: 24px;
}

QPushButton#dashboardMicButton HudIcon,
QPushButton#assistantMicButton HudIcon,
QPushButton#headerIconButton HudIcon {
    min-width: 24px;
    min-height: 24px;
}

QPushButton#dashboardCommandButton HudIcon,
QPushButton#dashboardRecentRow HudIcon,
QPushButton#newConversationButton HudIcon,
QPushButton#navButton HudIcon {
    min-width: 22px;
    min-height: 22px;
}

QLabel#navButtonLabel,
QLabel#buttonText,
QLabel#conversationRowTitle,
QLabel#conversationRowStamp,
QLabel#dashboardRecentTitle,
QLabel#dashboardRecentStamp {
    background: transparent;
}

/* ============================================================
   FINAL NEXUS STABILITY / LEGIBILITY OVERRIDES
   ============================================================ */
QLabel#buttonText,
QLabel#dashboardActivityTitle,
QLabel#dashboardRecentTitle,
QLabel#dashboardRecentStamp,
QLabel#dashboardTimelineTitle,
QLabel#systemInfoValue,
QLabel#systemLiveStatLabel,
QLabel#systemLiveStatValue,
QLabel#systemHardwareLabel,
QLabel#systemHardwareValue,
QLabel#systemMetricDetail {
    min-width: 0px;
}

QLabel#systemInfoValue,
QLabel#systemLiveStatLabel,
QLabel#systemLiveStatValue,
QLabel#systemHardwareLabel,
QLabel#systemHardwareValue,
QLabel#dashboardActivityTitle,
QLabel#dashboardRecentTitle,
QLabel#dashboardTimelineTitle,
QLabel#buttonText {
    font-size: 9px;
}

QTextEdit#assistantOutput,
QTextEdit#activityOutput,
QPlainTextEdit#systemLogsOutput,
QPlainTextEdit#assistantInput,
QPlainTextEdit#dashboardInput {
    min-width: 0px;
}

QPlainTextEdit#systemLogsOutput {
    white-space: pre-wrap;
}

QPushButton#headerIconButton {
    min-width: 40px;
    max-width: 40px;
    min-height: 40px;
    max-height: 40px;
}

QPushButton#assistantMicButton {
    min-width: 42px;
    max-width: 42px;
    min-height: 42px;
    max-height: 42px;
    border-radius: 21px;
}

QPushButton#dashboardMicButton {
    min-width: 44px;
    max-width: 44px;
    min-height: 44px;
    max-height: 44px;
    border-radius: 22px;
}

QPushButton#dashboardCommandButton {
    min-height: 44px;
    padding: 4px 7px;
}

QPushButton#dashboardCommandButton HudIcon,
QPushButton#dashboardRecentRow HudIcon,
QPushButton#navButton HudIcon,
QPushButton#headerIconButton HudIcon,
QPushButton#assistantMicButton HudIcon,
QPushButton#dashboardMicButton HudIcon {
    min-width: 18px;
    min-height: 18px;
}

QFrame#systemHeaderIconBadge {
    min-width: 46px;
    max-width: 46px;
    min-height: 46px;
    max-height: 46px;
}

QFrame#systemMetricIconBadge,
QFrame#systemStatIconBadge,
QFrame#systemHardwareIconBadge {
    min-width: 38px;
    max-width: 38px;
    min-height: 38px;
    max-height: 38px;
}

QFrame#systemReferencePanel {
    min-width: 0px;
}

QLabel#systemReferenceTitle,
QLabel#systemReferenceTitleSmall,
QLabel#systemReferenceSubtitle,
QLabel#hudPanelTitle,
QLabel#activityTitle,
QLabel#heroTitle {
    min-width: 0px;
}

QFrame#compactMetricRow {
    background: transparent;
    border: none;
    border-bottom: 1px solid #103044;
}

QLabel#compactMetricValue {
    font-size: 11px;
    font-weight: 700;
}

QProgressBar#compactMetricBar {
    background: #07131e;
    border: none;
    border-radius: 3px;
    max-height: 7px;
}

QProgressBar#compactMetricBar::chunk {
    background: #20c9ee;
    border-radius: 3px;
}

/* Focused utility windows: the dashboard remains the only main page. */
QDialog#toolPopup {
    background-color: #020b10;
    border: 1px solid #12617d;
}

QDialog#toolPopup QWidget {
    selection-background-color: #0b3b57;
    selection-color: #e8f8ff;
}

QMenu#dashboardToolsMenu {
    background-color: #03121c;
    border: 1px solid #1683a7;
    padding: 6px;
    color: #cce8f5;
}

QMenu#dashboardToolsMenu::item {
    padding: 9px 24px;
    border-radius: 5px;
}

QMenu#dashboardToolsMenu::item:selected {
    background-color: #0a2d42;
    color: #4bdcff;
}

QDialog#customizeDialog {
    background-color: #020b10;
    border: 1px solid #1783a4;
}

QFrame#customizePanel {
    background-color: rgba(3, 18, 28, 245);
    border: 1px solid #124b62;
    border-radius: 9px;
}

QLabel#customizeFieldLabel {
    color: #69a9c0;
    font-family: "Consolas";
    font-size: 9px;
    font-weight: 600;
    letter-spacing: 1px;
}

QLineEdit#customizeIdentity,
QLineEdit#customizeInput {
    background-color: #020f17;
    border: 1px solid #15506a;
    border-radius: 6px;
    color: #d8f3ff;
    min-height: 36px;
    padding: 4px 10px;
}

QLineEdit#customizeIdentity[readOnly="true"] {
    color: #45d9ff;
    font-weight: 700;
    letter-spacing: 2px;
}

QPushButton#accentColorButton {
    text-align: left;
    font-family: "Consolas";
    font-weight: 700;
}

QPushButton#interruptButton {
    background-color: #190611;
    border: 1px solid #a2164b;
    border-radius: 7px;
    color: #ff4778;
    font-family: "Consolas";
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 1px;
}

QPushButton#interruptButton:hover {
    background-color: #2a0a19;
    border-color: #ff376e;
    color: #ff7598;
}

QPushButton#interruptButton:pressed {
    background-color: #380d20;
}

"""
