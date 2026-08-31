import QtQuick
import QtQuick.Layouts
import QtQuick.Controls
import QtCore
import org.kde.plasma.plasmoid
import org.kde.plasma.core as PlasmaCore
import org.kde.plasma.components as PlasmaComponents3

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
            var homePath = StandardPaths.writableLocation(StandardPaths.HomeLocation);
            var execUrl = "file://" + homePath + "/.local/bin/qhealth";
            Qt.openUrlExternally(execUrl);
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
                text: root.isPaused ? "PAUSED" : (root.isIdle ? "IDLE" : root.todayDuration)
                font.bold: true
                font.pixelSize: 12
                color: root.isPaused ? "#fbbf24" : (root.isIdle ? "#94a3b8" : "#34d399")
            }

            PlasmaComponents3.Label {
                visible: !root.isIdle && !root.isPaused && root.liveWpm > 0
                text: "• " + root.liveWpm + " WPM"
                font.pixelSize: 11
                color: "#22d3ee"
            }
        }

        PlasmaCore.ToolTipArea {
            anchors.fill: parent
            mainText: "QHealth — Screen Time"
            subText: "Today: " + root.todayDuration + "\nActive: " + root.activeApp + (root.liveWpm > 0 ? "\nTyping: " + root.liveWpm + " WPM" : "") + "\n\nClick to open full QHealth dashboard."
        }
    }
}
