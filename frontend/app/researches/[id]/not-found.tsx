import Link from "next/link";

export default function ResearchNotFound() {
  return (
    <main className="wide">
      <h1>Pesquisa não encontrada</h1>
      <div className="card">
        <p>
          A API retornou 404 para este identificador (ou o UUID é inválido — a API responde 422
          nesse caso).
        </p>
        <Link href="/researches" className="btn primary">
          Voltar para pesquisas
        </Link>
      </div>
    </main>
  );
}
