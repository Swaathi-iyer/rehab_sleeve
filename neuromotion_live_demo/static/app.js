const MAX_POINTS = 160;

let emgHistory = [];
let gyroHistory = [];


function drawFusionChart() {

    const canvas = document.getElementById("fusionChart");
    const ctx = canvas.getContext("2d");

    const width = canvas.width;
    const height = canvas.height;

    ctx.clearRect(0, 0, width, height);

    ctx.strokeStyle = "rgba(255,255,255,0.045)";
    ctx.lineWidth = 1;

    for (let i = 1; i < 5; i++) {
        const y = (height / 5) * i;
        ctx.beginPath();
        ctx.moveTo(0, y);
        ctx.lineTo(width, y);
        ctx.stroke();
    }

    drawLine(
        emgHistory,
        "#22d3ee",
        0,
        Math.max(400, ...emgHistory, 400)
    );

    const maxGyro = Math.max(
        80,
        ...gyroHistory.map(Math.abs)
    );

    drawLine(
        gyroHistory,
        "#8b5cf6",
        -maxGyro,
        maxGyro
    );


    function drawLine(values, color, min, max) {

        if (values.length < 2) {
            return;
        }

        ctx.beginPath();

        values.forEach((value, index) => {

            const x =
                index /
                (MAX_POINTS - 1) *
                width;

            const y =
                height -
                ((value - min) / (max - min)) *
                (height - 25) -
                12;

            if (index === 0) {
                ctx.moveTo(x, y);
            }
            else {
                ctx.lineTo(x, y);
            }
        });

        ctx.strokeStyle = color;
        ctx.lineWidth = 2;
        ctx.shadowColor = color;
        ctx.shadowBlur = 8;
        ctx.stroke();
        ctx.shadowBlur = 0;
    }
}


async function setLoad() {

    const value = parseFloat(
        document.getElementById("loadInput").value || "0"
    );

    await fetch(
        "/api/load",
        {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                load_kg: value
            })
        }
    );
}


async function setBaseline() {

    const emg = parseFloat(
        document.getElementById("baselineEmgInput").value || "300"
    );

    const repTime = parseFloat(
        document.getElementById("baselineTimeInput").value || "4"
    );

    await fetch(
        "/api/baseline",
        {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                baseline_emg: emg,
                baseline_rep_time: repTime
            })
        }
    );
}


async function update() {

    try {

        const data =
            await fetch("/api/state")
            .then(response => response.json());


        document.getElementById("arduinoDot").className =
            "dot " +
            (data.arduino_connected ? "connected" : "disconnected");


        document.getElementById("espDot").className =
            "dot " +
            (data.esp32_connected ? "connected" : "disconnected");


        document.getElementById("rep").textContent =
            data.reps;


        document.getElementById("phase").textContent =
            data.wrist_state;


        document.getElementById("repTime").textContent =
            Number(data.last_rep_time_s).toFixed(2) + " s";


        document.getElementById("controlRepTime").textContent =
            Number(data.last_rep_time_s).toFixed(2) + " s";


        document.getElementById("terminalDecel").textContent =
            Number(data.last_terminal_decel).toFixed(0) + " °/s²";


        document.getElementById("emg").textContent =
            data.emg_filtered;


        document.getElementById("emgFill").style.width =
            Math.min(
                100,
                Number(data.emg_filtered) / 10.23
            ) + "%";


        document.getElementById("muscle").textContent =
            data.muscle_state;


        document.getElementById("fatigue").textContent =
            data.fatigue_status;


        document.getElementById("control").textContent =
            data.control_status;


        document.getElementById("gx").textContent =
            Number(data.gx).toFixed(1);


        document.getElementById("gy").textContent =
            Number(data.gy).toFixed(1);


        document.getElementById("gz").textContent =
            Number(data.gz).toFixed(1);


        document.getElementById("decision").textContent =
            data.baseline_decision;


        document.getElementById("progression").textContent =
            data.progression_status;


        document.getElementById("guidance").textContent =
            data.exercise_guidance;


        document.getElementById("csvName").textContent =
            data.csv_file;


        document.getElementById("ruleFatigue").textContent =
            data.fatigue_status;


        document.getElementById("ruleControl").textContent =
            data.control_status === "GOOD"
            ? "YES"
            : data.control_status === "DEGRADED"
            ? "NO"
            : "--";


        document.getElementById("ruleLoad").textContent =
            Number(data.current_load_kg).toFixed(1) + " kg";


        document.getElementById("baselineSource").textContent =
            data.baseline_source;


        const ruleTitle =
            document.getElementById("ruleTitle");

        const ruleCallout =
            document.getElementById("ruleCallout");

        const decisionText =
            document.getElementById("decisionText");


        if (data.fatigue_status === "TREND" &&
            data.control_status === "GOOD") {

            ruleTitle.textContent =
                "Suspected substitution pattern";

            ruleCallout.textContent =
                "Mean EMG rose above the demo baseline while movement control remained preserved → WITHHOLD.";

            decisionText.textContent =
                "Rep withheld from the baseline update for the demo logic.";
        }

        else if (data.control_status === "DEGRADED") {

            ruleTitle.textContent =
                "Movement control degraded";

            ruleCallout.textContent =
                "Rep timing or terminal movement behavior departed from the demo baseline.";

            decisionText.textContent =
                "Rep admitted as genuine control degradation.";
        }

        else {

            ruleTitle.textContent =
                "No suspected substitution";

            ruleCallout.textContent =
                "Rep remains within the assumed/live-anchored demo baseline.";

            decisionText.textContent =
                "Rep admitted as a normal baseline-consistent repetition.";
        }


        const rows = data.rep_rows || [];
        const tbody = document.getElementById("repRows");

        tbody.innerHTML = "";


        rows
        .slice()
        .reverse()
        .forEach(row => {

            const tr =
                document.createElement("tr");

            tr.innerHTML = `
                <td>${row.rep}</td>
                <td>${Number(row.rep_time_s).toFixed(2)} s</td>
                <td>${Number(row.mean_emg).toFixed(1)}</td>
                <td>${Number(row.peak_emg).toFixed(1)}</td>
                <td>${Number(row.normalized_emg_pct).toFixed(1)}%</td>
                <td>${Number(row.terminal_decel_proxy_dps2).toFixed(0)}</td>
                <td>${Number(row.current_load_kg).toFixed(2)} kg</td>
                <td>${row.fatigue_status}</td>
                <td>${row.control_status}</td>
                <td>${row.baseline_decision}</td>
            `;

            tbody.appendChild(tr);
        });


        document.getElementById("summaryReps").textContent =
            data.reps;


        const completedRows =
            rows.filter(row => Number(row.rep_time_s) > 0);


        const avgTime =
            completedRows.length
            ? completedRows.reduce(
                (sum, row) =>
                    sum + Number(row.rep_time_s),
                0
              ) / completedRows.length
            : 0;


        document.getElementById("summaryAvgTime").textContent =
            completedRows.length
            ? avgTime.toFixed(2) + " s"
            : "--";


        document.getElementById("summaryMeanEmg").textContent =
            data.last_mean_emg
            ? Number(data.last_mean_emg).toFixed(1)
            : "--";


        document.getElementById("summaryNormalized").textContent =
            data.last_normalized_emg_pct
            ? Number(data.last_normalized_emg_pct).toFixed(1) + "%"
            : "--";


        document.getElementById("summaryAdmitted").textContent =
            data.admitted_count;


        document.getElementById("summaryWithheld").textContent =
            data.withheld_count;


        emgHistory.push(
            Number(data.emg_filtered)
        );


        gyroHistory.push(
            Number(data.gy)
        );


        if (emgHistory.length > MAX_POINTS) {
            emgHistory.shift();
        }


        if (gyroHistory.length > MAX_POINTS) {
            gyroHistory.shift();
        }


        drawFusionChart();

    }

    catch(error) {
        console.log(error);
    }
}


setInterval(update, 100);

update();