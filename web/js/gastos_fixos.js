// Caminho: web/js/gastos_fixos.js
let listaGastosCache = [];

function formatarBRL(valor) {
    return Number(valor || 0).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

function exibirAlertaGasto(msg, tipo = "success") {
    const box = document.getElementById("gasto-alert");
    if (!box) return;
    box.style.display = "block";
    box.className = `alert-box ${tipo === "success" ? "alert-success" : "alert-error"}`;
    box.textContent = msg;
}

document.addEventListener("DOMContentLoaded", () => {
    carregarGastosFixos();

    const form = document.getElementById("form-gasto-fixo");
    const btnCancelar = document.getElementById("btn-cancelar-gasto");
    const btnLogout = document.getElementById("btn-logout");

    if (form) form.addEventListener("submit", salvarGastoFixo);
    if (btnCancelar) btnCancelar.addEventListener("click", limparFormularioGasto);
    if (btnLogout) {
        btnLogout.addEventListener("click", async () => {
            await fetch("/api/auth/logout", { method: "POST" });
            localStorage.removeItem("usuario_logado");
            window.location.href = "/";
        });
    }
});

async function carregarGastosFixos() {
    try {
        const res = await fetch("/api/gastos-fixos", { cache: "no-store" });
        if (res.status === 401) {
            window.location.href = "/";
            return;
        }
        const data = await res.json();
        if (!data.sucesso) return;

        listaGastosCache = data.gastos_fixos || [];
        document.getElementById("total-gastos-fixos").textContent = formatarBRL(data.resumo.total_gastos_fixos);
        renderizarTabelaGastos();
    } catch (err) {
        console.error("Erro ao carregar gastos fixos:", err);
    }
}

function renderizarTabelaGastos() {
    const tbody = document.getElementById("tabela-gastos-body");
    if (!tbody) return;

    if (listaGastosCache.length === 0) {
        tbody.innerHTML = `<tr><td colspan="5" class="empty-msg">Nenhum gasto fixo cadastrado. Adicione ao lado ou envie no Telegram: "Cadastrar meu aluguel como gasto fixo no valor de R$ 1500 todo dia 10".</td></tr>`;
        return;
    }

    tbody.innerHTML = listaGastosCache.map((item) => `
        <tr>
            <td><strong>${item.description}</strong></td>
            <td>Todo dia <strong>${item.due_day}</strong></td>
            <td class="text-red" style="font-weight:700;">- ${formatarBRL(item.amount)}</td>
            <td>
                <span class="badge-tipo ${item.is_active ? "badge-despesa" : "badge-receita"}">
                    ${item.is_active ? "Ativo" : "Inativo"}
                </span>
            </td>
            <td>
                <button type="button" class="btn-refresh" style="padding:4px 8px; font-size:0.8rem;" onclick="prepararEdicaoGasto(${item.id})">✏️ Editar</button>
                <button type="button" class="btn-logout" style="width:auto; padding:4px 8px; font-size:0.8rem;" onclick="excluirGastoFixo(${item.id})">🗑️ Excluir</button>
            </td>
        </tr>
    `).join("");
}

async function salvarGastoFixo(e) {
    e.preventDefault();
    const id = document.getElementById("gasto-id").value;
    const description = document.getElementById("gasto-descricao").value.trim();
    const amount = parseFloat(document.getElementById("gasto-valor").value);
    const due_day = parseInt(document.getElementById("gasto-dia").value, 10);
    const is_active = document.getElementById("gasto-ativo").value === "true";

    const url = id ? `/api/gastos-fixos/${id}` : "/api/gastos-fixos";
    const metodo = id ? "PUT" : "POST";

    try {
        const res = await fetch(url, {
            method: metodo,
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ description, amount, due_day, is_active })
        });
        const data = await res.json();

        if (res.ok && data.sucesso) {
            exibirAlertaGasto(id ? "Gasto fixo atualizado com sucesso!" : "Gasto fixo cadastrado com sucesso!", "success");
            limparFormularioGasto();
            localStorage.setItem("ultima_atualizacao_financeira", Date.now().toString());
            carregarGastosFixos();
        } else {
            exibirAlertaGasto(data.erro || "Erro ao salvar gasto fixo.", "error");
        }
    } catch (err) {
        exibirAlertaGasto("Erro de conexão com o servidor.", "error");
    }
}

function prepararEdicaoGasto(id) {
    const item = listaGastosCache.find((g) => g.id === id);
    if (!item) return;

    document.getElementById("form-gasto-titulo").textContent = "✏️ Editar Gasto Fixo";
    document.getElementById("gasto-id").value = item.id;
    document.getElementById("gasto-descricao").value = item.description;
    document.getElementById("gasto-valor").value = item.amount;
    document.getElementById("gasto-dia").value = item.due_day;
    document.getElementById("gasto-ativo").value = item.is_active ? "true" : "false";
    document.getElementById("btn-salvar-gasto").textContent = "Atualizar Gasto Fixo";
    document.getElementById("btn-cancelar-gasto").style.display = "block";
}

function limparFormularioGasto() {
    document.getElementById("form-gasto-fixo").reset();
    document.getElementById("gasto-id").value = "";
    document.getElementById("form-gasto-titulo").textContent = "➕ Cadastrar Novo Gasto Fixo";
    document.getElementById("btn-salvar-gasto").textContent = "Salvar Gasto Fixo";
    document.getElementById("btn-cancelar-gasto").style.display = "none";
}

async function excluirGastoFixo(id) {
    if (!confirm("Deseja realmente excluir este gasto fixo?")) return;
    try {
        const res = await fetch(`/api/gastos-fixos/${id}`, { method: "DELETE" });
        const data = await res.json();
        if (res.ok && data.sucesso) {
            localStorage.setItem("ultima_atualizacao_financeira", Date.now().toString());
            carregarGastosFixos();
        }
    } catch (err) {
        alert("Erro ao excluir registro.");
    }
}