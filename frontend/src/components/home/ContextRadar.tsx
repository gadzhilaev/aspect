const STEPS = [
  { title: 'Экспортные ограничения', detail: 'Сигнал' },
  { title: 'Shenzhen X', detail: 'Поставщик' },
  { title: 'Электронный модуль B', detail: 'Компонент' },
  { title: 'Линия №2', detail: 'Производство' },
  { title: '24% выпуска', detail: 'Под риском' },
] as const

export function ContextRadar() {
  return (
    <div className="radar" aria-label="Демонстрационная цепочка влияния">
      <div className="radar-top">
        <p className="radar-label">Как Аспект читает событие</p>
        <p className="radar-tagline">Новость → ваша цепочка → влияние на выпуск</p>
      </div>

      <ol className="radar-chain">
        {STEPS.map((step, index) => (
          <li key={step.title} className="radar-step">
            <div className="radar-step-dot" aria-hidden>
              <span />
            </div>
            <div className="radar-step-body">
              <div className="radar-step-detail">{step.detail}</div>
              <div className="radar-step-title">{step.title}</div>
            </div>
            {index < STEPS.length - 1 ? <div className="radar-step-line" aria-hidden /> : null}
          </li>
        ))}
      </ol>

      <div className="radar-metrics">
        <div className="radar-metric">
          <div className="radar-metric-label">Влияние</div>
          <div className="radar-metric-value">
            87<span>/100</span>
          </div>
        </div>
        <div className="radar-metric">
          <div className="radar-metric-label">Уверенность</div>
          <div className="radar-metric-value">85%</div>
        </div>
        <div className="radar-metric radar-metric-wide">
          <div className="radar-metric-label">Вывод</div>
          <div className="radar-metric-note">
            Линия №2 под ударом — сценарии замещения и запаса доступны в разборе.
          </div>
        </div>
      </div>
    </div>
  )
}
