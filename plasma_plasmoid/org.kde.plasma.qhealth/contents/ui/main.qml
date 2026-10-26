import QtQuick
import QtQuick.Layouts
import QtQuick.Controls
import QtCore
import org.kde.plasma.plasmoid
import org.kde.plasma.core as PlasmaCore
import org.kde.plasma.components as PlasmaComponents3
import org.kde.plasma.plasma5support as P5Support
import org.kde.kirigami as Kirigami

PlasmoidItem {
    id: root

    preferredRepresentation: compactRepresentation

    property string todayDuration: "0m"
    property int liveWpm: 0
    property string activeApp: "Desktop"
    property bool isIdle: false
    property bool isPaused: false

    function refreshStats() {
        var doc = new XMLHttpRequest();
        doc.onreadystatechange = function() {
            if (doc.readyState === XMLHttpRequest.DONE) {
                if (doc.status === 200 || doc.status === 0) {
                    try {
                        var data = JSON.parse(doc.responseText);
                        root.todayDuration = data.today_duration_formatted || "0m";
                        root.liveWpm = data.live_wpm || 0;
                        root.activeApp = data.active_app || "Desktop";
                        root.isIdle = data.is_idle || false;
                        root.isPaused = data.is_paused || false;
                    } catch (e) {}
                }
            }
        };
        var dataPath = StandardPaths.writableLocation(StandardPaths.GenericDataLocation);
        var url = "file://" + dataPath + "/qhealth/live_state.json";
        doc.open("GET", url);
        doc.send();
    }

    // Runs `qhealth` whether it is installed system-wide or per user (~/.local/bin may not be on plasmashell's PATH)
    P5Support.DataSource {
        id: launcher
        engine: "executable"
        connectedSources: []
        onNewData: (sourceName, data) => launcher.disconnectSource(sourceName)
        function open() {
            connectSource("sh -c 'command -v qhealth >/dev/null && exec qhealth || exec \"$HOME/.local/bin/qhealth\"'")
        }
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

        onClicked: launcher.open()

        RowLayout {
            id: contentRow
            anchors.centerIn: parent
            spacing: 6

            Kirigami.Icon {
                source: "qhealth"
                fallback: "chronometer"
                implicitWidth: Kirigami.Units.iconSizes.small
                implicitHeight: Kirigami.Units.iconSizes.small
            }

            PlasmaComponents3.Label {
                text: root.isPaused ? "PAUSED" : (root.isIdle ? "IDLE" : root.todayDuration)
                font.bold: true
                font.pixelSize: 12
                color: root.isPaused ? Kirigami.Theme.neutralTextColor : (root.isIdle ? Kirigami.Theme.disabledTextColor : Kirigami.Theme.positiveTextColor)
            }

            PlasmaComponents3.Label {
                visible: !root.isIdle && !root.isPaused && root.liveWpm > 0
                text: "• " + root.liveWpm + " WPM"
                font.pixelSize: 11
                opacity: 0.8
            }
        }

        PlasmaCore.ToolTipArea {
            anchors.fill: parent
            mainText: "QHealth — Screen Time"
            subText: "Today: " + root.todayDuration + "\nActive: " + root.activeApp + (root.liveWpm > 0 ? "\nTyping: " + root.liveWpm + " WPM" : "") + "\n\nClick to open full QHealth dashboard."
        }
    }
}
