// Caminho: web/js/dashboard.js
function formatarMoedaBRL(valor) {
    return Number(valor || 0).toLocaleString("pt-BR", {
        style: "currency",
        currency: "BRL"
    });
}

document.addEventListener("DOMContentLoaded", () => {
    carregarStatsDashboard();

    // Sincronização em tempo real quando uma transação é feita no Chat IA (mesma aba ou outra aba)
    window.addEventListener("storage", (e) => {
        if (e.key === "ultima_atualizacao_financeira") {
            carregarStatsDashboard();
        }
    });

    document.addEventListener("visibilitychange", () => {
        if (!document.hidden) {
            carregarStatsDashboard();
        }
    });

    // Polling leve a cada 6 segundos para refletir mensagens vindas do celular/WhatsApp
    setInterval(carregarStatsDashboard, 6000);

    const btnRefresh = document.getElementById("btn-refresh-dash");
    if (btnRefresh) {
        btnRefresh.addEventListener("click", carregarStatsDashboard);
    }

    const formTransacao = document.getElementById("form-nova-transacao");
    if (formTransacao) {
        formTransacao.addEventListener("submit", registrarTransacaoManual);
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

async function carregarStatsDashboard() {
    try {
        const res = await fetch("/api/dashboard/stats", { cache: "no-store" });
        if (res.status === 401) {
            window.location.href = "/";
            return;
        }
        const data = await res.json();
        if (!data.sucesso) return;

        if (data.usuario && data.usuario.nome) {
            const elNome = document.getElementById("dash-user-name");
            if (elNome) elNome.textContent = `Olá, ${data.usuario.nome}`;
        }

        renderizarCardsResumo(data.resumo);
        renderizarCategorias(data.resumo.despesas_por_categoria, data.resumo.total_despesas);
        renderizarTabelaTransacoes(data.transacoes);
    } catch (err) {
        console.error("Erro ao sincronizar Dashboard:", err);
    }
}

function renderizarCardsResumo(resumo) {
    const elSaldo = document.getElementById("metric-saldo");
    const elReceitas = document.getElementById("metric-receitas");
    const elDespesas = document.getElementById("metric-despesas");
    const elStatus = document.getElementById("metric-status-orca");
    const elQtd = document.getElementById("metric-qtd-lancamentos");

    if (elSaldo) {
        elSaldo.textContent = formatarMoedaBRL(resumo.saldo);
        elSaldo.className = `metric-value ${resumo.saldo < 0 ? "text-red" : "text-green"}`;
    }
    if (elReceitas) elReceitas.textContent = formatarMoedaBRL(resumo.total_receitas);
    if (elDespesas) elDespesas.textContent = formatarMoedaBRL(resumo.total_despesas);

    if (elStatus) {
        elStatus.textContent = resumo.saldo < 0
            ? "⚠️ Atenção: Saldo negativo no período"
            : "✅ Orçamento com saldo positivo";
    }
    if (elQtd) {
        elQtd.textContent = `${resumo.total_lancamentos || 0} movimentações registradas`;
    }
}

function renderizarCategorias(categorias, totalDespesas) {
    const container = document.getElementById("categorias-container");
    if (!container) return;

    if (!categorias || categorias.length === 0) {
        container.innerHTML = `<p class="empty-msg">Nenhuma despesa categorizada ainda.</p>`;
        return;
    }

    container.innerHTML = categorias.map((c) => {
        const perc = totalDespesas > 0 ? Math.min(100, (c.total / totalDespesas) * 100) : 0;
        return `
            <div class="cat-item">
                <div class="cat-header">
                    <span>${c.categoria}</span>
                    <strong>${formatarMoedaBRL(c.total)} (${perc.toFixed(0)}%)</strong>
                </div>
                <div class="cat-bar-bg">
                    <div class="cat-bar-fill" style="width: ${perc}%;"></div>
                </div>
            </div>
        `;
    }).join("");
}

function renderizarTabelaTransacoes(transacoes) {
    const tbody = document.getElementById("tabela-transacoes-body");
    if (!tbody) return;

    if (!transacoes || transacoes.length === 0) {
        tbody.innerHTML = `<tr><td colspan="5" class="empty-msg">Nenhuma movimentação registrada. Experimente digitar no Assistente IA: "Comprei uma camiseta de 60".</td></tr>`;
        return;
    }

    tbody.innerHTML = transacoes.map((t) => {
        const ehReceita = t.tipo === "receita";
        const dataFormatada = t.data_transacao
            ? new Date(t.data_transacao.replace(" ", "T")).toLocaleDateString("pt-BR")
            : "-";
        return `
            <tr>
                <td>${dataFormatada}</td>
                <td>${t.descricao || "-"}</td>
                <td>${t.categoria}</td>
                <td>
                    <span class="badge-tipo ${ehReceita ? "badge-receita" : "badge-despesa"}">
                        ${ehReceita ? "Entrada" : "Saída"}
                    </span>
                </td>
                <td class="${ehReceita ? "text-green" : "text-red"}" style="font-weight: 700;">
                    ${ehReceita ? "+" : "-"} ${formatarMoedaBRL(t.valor)}
                </td>
            </tr>
        `;
    }).join("");
}

async function registrarTransacaoManual(e) {
    e.preventDefault();
    const tipo = document.getElementById("trans-tipo").value;
    const valor = parseFloat(document.getElementById("trans-valor").value);
    const categoria = document.getElementById("trans-categoria").value;
    const descricao = document.getElementById("trans-descricao").value.trim();
    const alertBox = document.getElementById("dash-alert");

    try {
        const res = await fetch("/api/transacoes", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ tipo, valor, categoria, descricao, moeda: "BRL" })
        });
        const data = await res.json();
        alertBox.style.display = "block";

        if (res.ok && data.sucesso) {
            alertBox.className = "alert-box alert-success";
            alertBox.textContent = data.alerta || "Movimentação registrada com sucesso!";
            document.getElementById("form-nova-transacao").reset();
            localStorage.setItem("ultima_atualizacao_financeira", Date.now().toString());
            carregarStatsDashboard();
        } else {
            alertBox.className = "alert-box alert-error";
            alertBox.textContent = data.erro || "Erro ao salvar transação.";
        }
    } catch (err) {
        alertBox.style.display = "block";
        alertBox.className = "alert-box alert-error";
        alertBox.textContent = "Erro de conexão com o servidor.";
    }
}