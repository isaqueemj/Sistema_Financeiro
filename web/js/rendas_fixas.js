// Caminho: web/js/rendas_fixas.js
function formatarMoedaBRL(valor) {
    return Number(valor || 0).toLocaleString("pt-BR", {
        style: "currency",
        currency: "BRL"
    });
}

document.addEventListener("DOMContentLoaded", () => {
    carregarRendasFixas();

    const form = document.getElementById("form-renda-fixa") || document.querySelector("form");
    if (form) {
        form.addEventListener("submit", salvarRendaFixa);
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

function exibirAlertaRenda(mensagem, tipo = "success") {
    let box = document.getElementById("renda-alert") || document.querySelector(".alert-box");
    if (!box) {
        const form = document.querySelector("form");
        if (!form) return;
        box = document.createElement("div");
        box.id = "renda-alert";
        box.className = "alert-box";
        form.parentElement.insertBefore(box, form);
    }
    box.className = `alert-box ${tipo === "success" ? "alert-success" : "alert-error"}`;
    box.textContent = mensagem;
    box.style.display = "block";
    setTimeout(() => { box.style.display = "none"; }, 4000);
}

async function carregarRendasFixas() {
    const tbody =
        document.getElementById("tabela-rendas-body") ||
        document.getElementById("rendas-tbody") ||
        document.querySelector("table tbody");

    try {
        const res = await fetch(`/api/rendas-fixas?_t=${Date.now()}`, {
            method: "GET",
            credentials: "same-origin",
            cache: "no-store"
        });

        if (res.status === 401) {
            window.location.href = "/";
            return;
        }

        const data = await res.json();
        const lista = data.rendas_fixas || data.receitas_fixas || data.rendas || data.itens || [];

        const totalAtivo = lista
            .filter((item) => item.is_active !== false && item.ativo !== false)
            .reduce((acc, item) => acc + Number(item.valor ?? item.amount ?? 0), 0);

        const elTotal =
            document.getElementById("total-rendas-fixas") ||
            document.getElementById("metric-total-rendas") ||
            document.querySelector(".metric-value, .text-green");
        if (elTotal) {
            elTotal.textContent = formatarMoedaBRL(totalAtivo);
        }

        if (!tbody) return;

        if (lista.length === 0) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="5" class="empty-msg">
                        Nenhuma renda fixa cadastrada. Adicione ao lado ou envie no Telegram: "Meu salário é uma renda fixa de R$ 4000 todo dia 5".
                    </td>
                </tr>
            `;
            return;
        }

        tbody.innerHTML = lista.map((r) => {
            const id = r.id;
            const desc = r.descricao || r.description || "Renda Fixa";
            const dia = r.dia_recebimento || r.day_of_month || r.dia || 5;
            const valor = Number(r.valor ?? r.amount ?? 0);
            const ativo = r.is_active !== false && r.ativo !== false;

            return `
                <tr>
                    <td><strong>${desc}</strong></td>
                    <td>Todo dia ${dia}</td>
                    <td class="text-green" style="font-weight:700;">${formatarMoedaBRL(valor)}</td>
                    <td>
                        <span class="badge-tipo ${ativo ? "badge-receita" : "badge-despesa"}">
                            ${ativo ? "Ativa" : "Inativa"}
                        </span>
                    </td>
                    <td>
                        <button type="button" onclick="alternarStatusRenda(${id}, ${!ativo})"
                            style="background:transparent; border:1px solid #475569; color:#cbd5e1; padding:4px 8px; border-radius:6px; cursor:pointer; margin-right:6px;">
                            ${ativo ? "Pausar" : "Ativar"}
                        </button>
                        <button type="button" onclick="excluirRendaFixa(${id})"
                            style="background:rgba(239,68,68,0.18); border:1px solid #ef4444; color:#fca5a5; padding:4px 8px; border-radius:6px; cursor:pointer;">
                            Excluir
                        </button>
                    </td>
                </tr>
            `;
        }).join("");
    } catch (err) {
        console.error("Erro ao carregar rendas fixas:", err);
        if (tbody) {
            tbody.innerHTML = `<tr><td colspan="5" class="empty-msg">Não foi possível carregar as rendas fixas.</td></tr>`;
        }
    }
}

async function salvarRendaFixa(e) {
    e.preventDefault();
    const form = e.target;

    const inputDesc =
        document.getElementById("renda-descricao") ||
        document.getElementById("desc-renda") ||
        form.querySelector("input[type='text']");
    const inputsNum = form.querySelectorAll("input[type='number']");
    const inputValor = document.getElementById("renda-valor") || inputsNum[0];
    const inputDia = document.getElementById("renda-dia") || inputsNum[1];
    const selectAtivo = document.getElementById("renda-status") || form.querySelector("select");

    const descricao = (inputDesc?.value || "").trim();
    const valor = parseFloat(String(inputValor?.value || "0").replace(",", "."));
    const dia = parseInt(inputDia?.value || "5", 10);
    const is_active = selectAtivo ? !["false", "0", "inativo", "inativa"].includes(selectAtivo.value.toLowerCase()) : true;

    if (!descricao || isNaN(valor) || valor <= 0) {
        exibirAlertaRenda("Informe uma descrição válida e um valor maior que zero.", "error");
        return;
    }

    try {
        const res = await fetch("/api/rendas-fixas", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            credentials: "same-origin",
            body: JSON.stringify({
                descricao,
                description: descricao,
                valor,
                amount: valor,
                dia_recebimento: dia,
                day_of_month: dia,
                ativo: is_active,
                is_active
            })
        });
        const data = await res.json();

        if (res.ok && data.sucesso) {
            exibirAlertaRenda("Renda fixa cadastrada com sucesso!", "success");
            form.reset();
            localStorage.setItem("ultima_atualizacao_financeira", Date.now().toString());
            await carregarRendasFixas();
        } else {
            exibirAlertaRenda(data.erro || "Erro ao salvar renda fixa.", "error");
        }
    } catch (err) {
        exibirAlertaRenda("Erro de comunicação com o servidor.", "error");
    }
}

async function alternarStatusRenda(id, novoStatus) {
    await fetch(`/api/rendas-fixas/${id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        credentials: "same-origin",
        body: JSON.stringify({ is_active: novoStatus, ativo: novoStatus })
    });
    localStorage.setItem("ultima_atualizacao_financeira", Date.now().toString());
    carregarRendasFixas();
}

async function excluirRendaFixa(id) {
    await fetch(`/api/rendas-fixas/${id}`, {
        method: "DELETE",
        credentials: "same-origin"
    });
    localStorage.setItem("ultima_atualizacao_financeira", Date.now().toString());
    carregarRendasFixas();
}