// Caminho: web/js/assistente.js
function formatarMoeda(valor) {
    return Number(valor || 0).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

function formatarMarkdownParaHTML(texto) {
    if (!texto) return "";
    return texto
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
        .replace(/\*([^*]+)\*/g, "<strong>$1</strong>")
        .replace(/`([^`]+)`/g, "<code>$1</code>")
        .replace(/\n/g, "<br>");
}

document.addEventListener("DOMContentLoaded", () => {
    carregarDadosUsuarioESaldo();

    const chatForm = document.getElementById("chat-form");
    if (chatForm) {
        chatForm.addEventListener("submit", async (e) => {
            e.preventDefault();
            const input = document.getElementById("chat-input");
            const msg = input.value.trim();
            if (!msg) return;
            input.value = "";
            await enviarMensagemAoBot(msg);
        });
    }

    const btnLogout = document.getElementById("btn-logout");
    if (btnLogout) {
        btnLogout.addEventListener("click", async () => {
            await fetch("/api/auth/logout", { method: "POST" });
            localStorage.removeItem("usuario_logado");
            window.location.href = "/";
        });
    }
});

function preencherInput(texto) {
    const input = document.getElementById("chat-input");
    if (input) {
        input.value = texto;
        input.focus();
    }
}

function enviarComandoRapido(comando) {
    enviarMensagemAoBot(comando);
}

function adicionarBalaoMensagem(remetente, textoHTML, graficos = null) {
    const container = document.getElementById("chat-messages");
    const row = document.createElement("div");
    row.className = `msg-row ${remetente}`;

    const hora = new Date().toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
    const avatar = remetente === "user" ? "👤" : "🤖";

    const idGraficoUnico = `chat-chart-${Date.now()}`;
    let htmlGraficos = "";
    if (graficos) {
        htmlGraficos = `
            <div class="chat-charts-box">
                <div class="chat-chart-item"><canvas id="${idGraficoUnico}-pizza"></canvas></div>
                <div class="chat-chart-item"><canvas id="${idGraficoUnico}-barras"></canvas></div>
                <div class="chat-chart-item"><canvas id="${idGraficoUnico}-linha"></canvas></div>
            </div>
        `;
    }

    row.innerHTML = `
        <div class="msg-avatar">${avatar}</div>
        <div class="msg-bubble">
            <div>${textoHTML}</div>
            ${htmlGraficos}
            <span class="msg-time">${hora}</span>
        </div>
    `;

    container.appendChild(row);
    container.scrollTop = container.scrollHeight;

    if (graficos) {
        renderizarGraficosNoBalao(idGraficoUnico, graficos);
    }
}

function renderizarGraficosNoBalao(prefixoId, graficos) {
    const ctxPizza = document.getElementById(`${prefixoId}-pizza`);
    if (ctxPizza) {
        new Chart(ctxPizza, {
            type: "doughnut",
            data: {
                labels: graficos.pizza?.labels?.length ? graficos.pizza.labels : ["Sem gastos"],
                datasets: [{
                    data: graficos.pizza?.valores?.length ? graficos.pizza.valores : [1],
                    backgroundColor: ["#3b82f6", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6", "#ec4899"]
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { labels: { color: "#f8fafc", font: { size: 10 } } } }
            }
        });
    }

    const ctxBarras = document.getElementById(`${prefixoId}-barras`);
    if (ctxBarras) {
        new Chart(ctxBarras, {
            type: "bar",
            data: {
                labels: ["Entradas", "Saídas"],
                datasets: [{
                    label: "R$",
                    data: [graficos.colunas?.entradas?.[0] || 0, graficos.colunas?.saidas?.[0] || 0],
                    backgroundColor: ["#10b981", "#ef4444"],
                    borderRadius: 6
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { display: false } },
                scales: {
                    x: { ticks: { color: "#cbd5e1" } },
                    y: { ticks: { color: "#cbd5e1" } }
                }
            }
        });
    }

    const ctxLinha = document.getElementById(`${prefixoId}-linha`);
    if (ctxLinha) {
        new Chart(ctxLinha, {
            type: "line",
            data: {
                labels: graficos.evolucao?.labels || ["Hoje"],
                datasets: [{
                    label: "Saldo (R$)",
                    data: graficos.evolucao?.saldos || [0],
                    borderColor: "#3b82f6",
                    backgroundColor: "rgba(59, 130, 246, 0.2)",
                    fill: true,
                    tension: 0.3
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { labels: { color: "#f8fafc", font: { size: 10 } } } },
                scales: {
                    x: { ticks: { color: "#cbd5e1" } },
                    y: { ticks: { color: "#cbd5e1" } }
                }
            }
        });
    }
}

async function enviarMensagemAoBot(mensagem) {
    adicionarBalaoMensagem("user", formatarMarkdownParaHTML(mensagem));

    try {
        const res = await fetch("/api/chat", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ mensagem })
        });
        const data = await res.json();

        const textoBot = formatarMarkdownParaHTML(data.resposta || "Comando processado.");
        const graficosChat = data.exibir_graficos_web ? data.graficos : null;

        adicionarBalaoMensagem("bot", textoBot, graficosChat);
        await carregarDadosUsuarioESaldo();
    } catch (err) {
        adicionarBalaoMensagem("bot", "⚠️ Erro de comunicação com o servidor.");
    }
}

async function carregarDadosUsuarioESaldo() {
    try {
        const res = await fetch("/api/dashboard/stats", { cache: "no-store" });
        if (!res.ok) return;
        const data = await res.json();
        if (!data.sucesso) return;

        const resumo = data.resumo;
        const elSaldo = document.getElementById("chat-header-saldo");
        if (elSaldo) {
            elSaldo.textContent = formatarMoeda(resumo.saldo);
            elSaldo.className = resumo.saldo < 0 ? "text-red" : "text-green";
        }

        // Exibe o nome do usuário em destaque no cabeçalho do assistente
        const elGreeting = document.getElementById("chat-user-greeting");
        if (elGreeting && data.usuario && data.usuario.nome) {
            elGreeting.textContent = `Olá, ${data.usuario.nome}`;
        }
    } catch (e) {
        console.error("Erro ao carregar dados do usuário:", e);
    }
}