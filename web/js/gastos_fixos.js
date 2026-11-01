// Caminho: web/js/gastos_fixos.js
function formatarMoedaBRL(valor) {
    return Number(valor || 0).toLocaleString("pt-BR", {
        style: "currency",
        currency: "BRL"
    });
}

document.addEventListener("DOMContentLoaded", () => {
    carregarGastosFixos();

    const form = document.getElementById("form-gasto-fixo") || document.querySelector("form");
    if (form) {
        form.addEventListener("submit", salvarGastoFixo);
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

function exibirAlertaGasto(mensagem, tipo = "success") {
    let box = document.getElementById("gasto-alert") || document.querySelector(".alert-box");
    if (!box) {
        const form = document.querySelector("form");
        if (!form) return;
        box = document.createElement("div");
        box.id = "gasto-alert";
        box.className = "alert-box";
        form.parentElement.insertBefore(box, form);
    }
    box.className = `alert-box ${tipo === "success" ? "alert-success" : "alert-error"}`;
    box.textContent = mensagem;
    box.style.display = "block";
    setTimeout(() => { box.style.display = "none"; }, 4000);
}

async function carregarGastosFixos() {
    const tbody =
        document.getElementById("tabela-gastos-body") ||
        document.getElementById("gastos-tbody") ||
        document.querySelector("table tbody");

    try {
        const res = await fetch(`/api/gastos-fixos?_t=${Date.now()}`, {
            method: "GET",
            credentials: "same-origin",
            cache: "no-store"
        });

        if (res.status === 401) {
            window.location.href = "/";
            return;
        }

        const data = await res.json();
        const lista = data.gastos_fixos || data.despesas_fixas || data.gastos || data.itens || [];

        const totalAtivo = lista
            .filter((item) => item.is_active !== false && item.ativo !== false)
            .reduce((acc, item) => acc + Number(item.valor ?? item.amount ?? 0), 0);

        const elTotal =
            document.getElementById("total-gastos-fixos") ||
            document.getElementById("metric-total-gastos") ||
            document.querySelector(".metric-value, .text-red");
        if (elTotal) {
            elTotal.textContent = formatarMoedaBRL(totalAtivo);
        }

        if (!tbody) return;

        if (lista.length === 0) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="5" class="empty-msg">
                        Nenhum gasto fixo cadastrado. Adicione ao lado ou envie no Telegram: "Cadastrar meu aluguel como gasto fixo no valor de R$ 1500 todo dia 10".
                    </td>
                </tr>
            `;
            return;
        }

        tbody.innerHTML = lista.map((g) => {
            const id = g.id;
            const desc = g.descricao || g.description || "Gasto Fixo";
            const dia = g.dia_vencimento || g.due_day || g.dia || 10;
            const valor = Number(g.valor ?? g.amount ?? 0);
            const ativo = g.is_active !== false && g.ativo !== false;

            return `
                <tr>
                    <td><strong>${desc}</strong></td>
                    <td>Todo dia ${dia}</td>
                    <td class="text-red" style="font-weight:700;">${formatarMoedaBRL(valor)}</td>
                    <td>
                        <span class="badge-tipo ${ativo ? "badge-despesa" : "badge-receita"}">
                            ${ativo ? "Ativo" : "Inativo"}
                        </span>
                    </td>
                    <td>
                        <button type="button" onclick="alternarStatusGasto(${id}, ${!ativo})"
                            style="background:transparent; border:1px solid #475569; color:#cbd5e1; padding:4px 8px; border-radius:6px; cursor:pointer; margin-right:6px;">
                            ${ativo ? "Pausar" : "Ativar"}
                        </button>
                        <button type="button" onclick="excluirGastoFixo(${id})"
                            style="background:rgba(239,68,68,0.18); border:1px solid #ef4444; color:#fca5a5; padding:4px 8px; border-radius:6px; cursor:pointer;">
                            Excluir
                        </button>
                    </td>
                </tr>
            `;
        }).join("");
    } catch (err) {
        console.error("Erro ao carregar gastos fixos:", err);
        if (tbody) {
            tbody.innerHTML = `<tr><td colspan="5" class="empty-msg">Não foi possível carregar os gastos fixos.</td></tr>`;
        }
    }
}

async function salvarGastoFixo(e) {
    e.preventDefault();
    const form = e.target;

    const inputDesc =
        document.getElementById("gasto-descricao") ||
        document.getElementById("desc-gasto") ||
        form.querySelector("input[type='text']");
    const inputsNum = form.querySelectorAll("input[type='number']");
    const inputValor = document.getElementById("gasto-valor") || inputsNum[0];
    const inputDia = document.getElementById("gasto-dia") || inputsNum[1];
    const selectAtivo = document.getElementById("gasto-status") || form.querySelector("select");

    const descricao = (inputDesc?.value || "").trim();
    const valor = parseFloat(String(inputValor?.value || "0").replace(",", "."));
    const dia = parseInt(inputDia?.value || "10", 10);
    const is_active = selectAtivo ? !["false", "0", "inativo", "inativa"].includes(selectAtivo.value.toLowerCase()) : true;

    if (!descricao || isNaN(valor) || valor <= 0) {
        exibirAlertaGasto("Informe uma descrição válida e um valor maior que zero.", "error");
        return;
    }

    try {
        const res = await fetch("/api/gastos-fixos", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            credentials: "same-origin",
            body: JSON.stringify({
                descricao,
                description: descricao,
                valor,
                amount: valor,
                dia_vencimento: dia,
                due_day: dia,
                ativo: is_active,
                is_active
            })
        });
        const data = await res.json();

        if (res.ok && data.sucesso) {
            exibirAlertaGasto("Gasto fixo cadastrado com sucesso!", "success");
            form.reset();
            localStorage.setItem("ultima_atualizacao_financeira", Date.now().toString());
            await carregarGastosFixos();
        } else {
            exibirAlertaGasto(data.erro || "Erro ao salvar gasto fixo.", "error");
        }
    } catch (err) {
        exibirAlertaGasto("Erro de comunicação com o servidor.", "error");
    }
}

async function alternarStatusGasto(id, novoStatus) {
    await fetch(`/api/gastos-fixos/${id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        credentials: "same-origin",
        body: JSON.stringify({ is_active: novoStatus, ativo: novoStatus })
    });
    localStorage.setItem("ultima_atualizacao_financeira", Date.now().toString());
    carregarGastosFixos();
}

async function excluirGastoFixo(id) {
    await fetch(`/api/gastos-fixos/${id}`, {
        method: "DELETE",
        credentials: "same-origin"
    });
    localStorage.setItem("ultima_atualizacao_financeira", Date.now().toString());
    carregarGastosFixos();
}