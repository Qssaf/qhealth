import QtQuick
import QtQuick.Layouts
import QtQuick.Controls
import org.kde.plasma.plasmoid
import org.kde.plasma.core as PlasmaCore
import org.kde.plasma.components as PlasmaComponents3
import org.kde.plasma.plasma5support as P5Support

PlasmoidItem {
    id: root

    preferredRepresentation: compactRepresentation

    property string todayDuration: "0m"
    property int liveWpm: 0
    property string activeApp: "Desktop"
    property bool isIdle: false
    property bool isPaused: false
    property bool isOffline: false
    property bool noInput: false

    // Qt 6 refuses XMLHttpRequest on local files (unless QML_XHR_ALLOW_FILE_READ=1, which
    // plasmashell doesn't set), so read the daemon's state file through the executable engine.
    P5Support.DataSource {
        id: shell
        engine: "executable"
        connectedSources: []
        onNewData: (sourceName, data) => {
            disconnectSource(sourceName);
            if (sourceName !== root.stateCommand) {
                return;
            }
            if (data["exit code"] !== 0) {
                // File missing (clean shutdown) or older than 10s (daemon crashed or was killed)
                root.isOffline = true;
                return;
            }
            try {
                var state = JSON.parse(data["stdout"]);
                root.todayDuration = state.today_duration_formatted || "0m";
                root.liveWpm = state.live_wpm || 0;
                root.activeApp = state.active_app || "Desktop";
                root.isIdle = state.is_idle || false;
                root.isPaused = state.is_paused || false;
                root.noInput = state.input_access_denied || false;
                root.isOffline = false;
            } catch (e) {}
        }
    }

    // The daemon rewrites the file every second, so a file older than 10s is stale
    readonly property string stateCommand: "f=\"$HOME/.local/share/qhealth/live_state.json\"; "
        + "[ $(( $(date +%s) - $(stat -c %Y \"$f\") )) -lt 10 ] && cat \"$f\""

    function refreshStats() {
        shell.connectSource(root.stateCommand);
    }

    Timer {
        interval: 2000
        running: true
        repeat: true
        triggeredOnStart: true
        onTriggered: root.refreshStats()
    }

    compactRepresentation: MouseArea {
        id: compactRoot
        Layout.minimumWidth: contentRow.implicitWidth + 12
        Layout.preferredWidth: contentRow.implicitWidth + 12
        Layout.minimumHeight: 24

        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor

        onClicked: {
            // setsid -f detaches the GUI so the data engine isn't left holding its process
            shell.connectSource("setsid -f \"$HOME/.local/bin/qhealth\" >/dev/null 2>&1");
        }

        RowLayout {
            id: contentRow
            anchors.centerIn: parent
            spacing: 6

            PlasmaComponents3.Label {
                text: "⏱"
                font.pixelSize: 13
            }

            PlasmaComponents3.Label {
                text: root.isOffline ? "OFF" : (root.isPaused ? "PAUSED" : (root.noInput ? "NO INPUT" : (root.isIdle ? "IDLE" : root.todayDuration)))
                font.bold: true
                font.pixelSize: 12
                color: root.isOffline ? "#64748b" : (root.isPaused ? "#fbbf24" : (root.noInput ? "#f87171" : (root.isIdle ? "#94a3b8" : "#34d399")))
            }

            PlasmaComponents3.Label {
                visible: !root.isOffline && !root.isIdle && !root.isPaused && root.liveWpm > 0
                text: "• " + root.liveWpm + " WPM"
                font.pixelSize: 11
                color: "#22d3ee"
            }
        }

        PlasmaCore.ToolTipArea {
            anchors.fill: parent
            mainText: "QHealth — Screen Time"
            subText: root.isOffline ? "Tracking daemon is not running.\n\nClick to open QHealth."
                : root.noInput ? "Cannot read keyboard/mouse (/dev/input), so nothing is recorded.\nFix: sudo usermod -aG input $USER, then log out and back in."
                : "Today: " + root.todayDuration + "\nActive: " + root.activeApp + (root.liveWpm > 0 ? "\nTyping: " + root.liveWpm + " WPM" : "") + "\n\nClick to open full QHealth dashboard."
        }
    }
}
