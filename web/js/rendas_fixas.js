// Caminho: web/js/rendas_fixas.js
let listaRendasCache = [];

function formatarBRL(valor) {
    return Number(valor || 0).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

function exibirAlertaRenda(msg, tipo = "success") {
    const box = document.getElementById("renda-alert");
    if (!box) return;
    box.style.display = "block";
    box.className = `alert-box ${tipo === "success" ? "alert-success" : "alert-error"}`;
    box.textContent = msg;
}

document.addEventListener("DOMContentLoaded", () => {
    carregarRendasFixas();

    const form = document.getElementById("form-renda-fixa");
    const btnCancelar = document.getElementById("btn-cancelar-edicao");
    const btnLogout = document.getElementById("btn-logout");

    if (form) form.addEventListener("submit", salvarRendaFixa);
    if (btnCancelar) btnCancelar.addEventListener("click", limparFormularioRenda);
    if (btnLogout) {
        btnLogout.addEventListener("click", async () => {
            await fetch("/api/auth/logout", { method: "POST" });
            localStorage.removeItem("usuario_logado");
            window.location.href = "/";
        });
    }
});

async function carregarRendasFixas() {
    try {
        const res = await fetch("/api/rendas-fixas", { cache: "no-store" });
        if (res.status === 401) {
            window.location.href = "/";
            return;
        }
        const data = await res.json();
        if (!data.sucesso) return;

        listaRendasCache = data.rendas_fixas || [];
        document.getElementById("total-rendas-fixas").textContent = formatarBRL(data.resumo.total_rendas_fixas);
        renderizarTabelaRendas();
    } catch (err) {
        console.error("Erro ao carregar rendas fixas:", err);
    }
}

function renderizarTabelaRendas() {
    const tbody = document.getElementById("tabela-rendas-body");
    if (!tbody) return;

    if (listaRendasCache.length === 0) {
        tbody.innerHTML = `<tr><td colspan="5" class="empty-msg">Nenhuma renda fixa cadastrada. Adicione ao lado ou envie no Telegram: "Meu salário é uma renda fixa de R$ 4000".</td></tr>`;
        return;
    }

    tbody.innerHTML = listaRendasCache.map((item) => `
        <tr>
            <td><strong>${item.description}</strong></td>
            <td>Todo dia <strong>${item.day_of_month}</strong></td>
            <td class="text-green" style="font-weight:700;">${formatarBRL(item.amount)}</td>
            <td>
                <span class="badge-tipo ${item.is_active ? "badge-receita" : "badge-despesa"}">
                    ${item.is_active ? "Ativa" : "Inativa"}
                </span>
            </td>
            <td>
                <button type="button" class="btn-refresh" style="padding:4px 8px; font-size:0.8rem;" onclick="prepararEdicaoRenda(${item.id})">✏️ Editar</button>
                <button type="button" class="btn-logout" style="width:auto; padding:4px 8px; font-size:0.8rem;" onclick="excluirRendaFixa(${item.id})">🗑️ Excluir</button>
            </td>
        </tr>
    `).join("");
}

async function salvarRendaFixa(e) {
    e.preventDefault();
    const id = document.getElementById("renda-id").value;
    const description = document.getElementById("renda-descricao").value.trim();
    const amount = parseFloat(document.getElementById("renda-valor").value);
    const day_of_month = parseInt(document.getElementById("renda-dia").value, 10);
    const is_active = document.getElementById("renda-ativa").value === "true";

    const url = id ? `/api/rendas-fixas/${id}` : "/api/rendas-fixas";
    const metodo = id ? "PUT" : "POST";

    try {
        const res = await fetch(url, {
            method: metodo,
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ description, amount, day_of_month, is_active })
        });
        const data = await res.json();

        if (res.ok && data.sucesso) {
            exibirAlertaRenda(id ? "Renda fixa atualizada com sucesso!" : "Renda fixa cadastrada com sucesso!", "success");
            limparFormularioRenda();
            localStorage.setItem("ultima_atualizacao_financeira", Date.now().toString());
            carregarRendasFixas();
        } else {
            exibirAlertaRenda(data.erro || "Erro ao salvar renda fixa.", "error");
        }
    } catch (err) {
        exibirAlertaRenda("Erro de conexão com o servidor.", "error");
    }
}

function prepararEdicaoRenda(id) {
    const item = listaRendasCache.find((r) => r.id === id);
    if (!item) return;

    document.getElementById("form-renda-titulo").textContent = "✏️ Editar Renda Fixa";
    document.getElementById("renda-id").value = item.id;
    document.getElementById("renda-descricao").value = item.description;
    document.getElementById("renda-valor").value = item.amount;
    document.getElementById("renda-dia").value = item.day_of_month;
    document.getElementById("renda-ativa").value = item.is_active ? "true" : "false";
    document.getElementById("btn-salvar-renda").textContent = "Atualizar Renda Fixa";
    document.getElementById("btn-cancelar-edicao").style.display = "block";
}

function limparFormularioRenda() {
    document.getElementById("form-renda-fixa").reset();
    document.getElementById("renda-id").value = "";
    document.getElementById("form-renda-titulo").textContent = "➕ Cadastrar Nova Renda Fixa";
    document.getElementById("btn-salvar-renda").textContent = "Salvar Renda Fixa";
    document.getElementById("btn-cancelar-edicao").style.display = "none";
}

async function excluirRendaFixa(id) {
    if (!confirm("Deseja realmente excluir esta renda fixa?")) return;
    try {
        const res = await fetch(`/api/rendas-fixas/${id}`, { method: "DELETE" });
        const data = await res.json();
        if (res.ok && data.sucesso) {
            localStorage.setItem("ultima_atualizacao_financeira", Date.now().toString());
            carregarRendasFixas();
        }
    } catch (err) {
        alert("Erro ao excluir registro.");
    }
}