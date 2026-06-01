import {
  ArrowRight,
  Bot,
  BrainCircuit,
  Cloud,
  Database,
  FileSearch,
  FileText,
  GitBranch,
  ShieldCheck,
  Sparkles,
  Upload,
} from 'lucide-react'

const CAPABILITIES = [
  {
    icon: Upload,
    title: 'Ingestion and OCR',
    text: 'Upload PDFs and TIFF invoices into an AWS-backed intake flow ready for Textract extraction.',
    action: 'Upload invoices',
    target: 'upload',
  },
  {
    icon: GitBranch,
    title: 'Quality-aware routing',
    text: 'Track processing states as invoices move through validation, consolidation, and promotion.',
    action: 'View history',
    target: 'history',
  },
  {
    icon: Bot,
    title: 'Conversational analytics',
    text: 'Ask natural-language questions over Gold analytics with Bedrock and Athena behind the scenes.',
    action: 'Open chat',
    target: 'chat',
  },
]

const SERVICES = [
  { name: 'S3 data lake', icon: Cloud, tone: 's3' },
  { name: 'Textract OCR', icon: FileSearch, tone: 'textract' },
  { name: 'Step Functions', icon: GitBranch, tone: 'step-functions' },
  { name: 'Athena SQL', icon: Database, tone: 'athena' },
  { name: 'Bedrock AI', icon: BrainCircuit, tone: 'bedrock' },
]

export default function HomePage({ onNavigate }) {
  return (
    <div className="home-page">
      <section className="hero-panel">
        <div className="hero-content">
          <span className="eyebrow">
            <Sparkles size={16} />
            Cloud-native invoice intelligence
          </span>
          <h1>Invoice Intelligence</h1>
          <p>
            A serverless AWS analytics platform for invoice ingestion, OCR extraction,
            quality-aware routing, and conversational Gold analytics.
          </p>
          <div className="hero-actions">
            <button className="btn-primary btn-with-icon" onClick={() => onNavigate('upload')}>
              <Upload size={17} />
              Upload invoices
            </button>
            <button className="btn-ghost btn-with-icon" onClick={() => onNavigate('chat')}>
              <Bot size={17} />
              Ask analytics
            </button>
          </div>
        </div>

        <div className="architecture-panel" aria-label="Pipeline architecture summary">
          <div className="architecture-node architecture-node--accent">
            <FileText size={18} />
            Raw invoices
          </div>
          <div className="architecture-rail" />
          <div className="architecture-node">
            <FileSearch size={18} />
            OCR extraction
          </div>
          <div className="architecture-rail" />
          <div className="architecture-node architecture-node--ai">
            <Database size={18} />
            Gold analytics
          </div>
        </div>
      </section>

      <section className="service-strip" aria-label="AWS services">
        {SERVICES.map(service => {
          const Icon = service.icon
          return (
            <div key={service.name} className={`service-chip service-chip--${service.tone}`}>
              <Icon size={17} />
              <span>{service.name}</span>
            </div>
          )
        })}
      </section>

      <section className="capability-grid">
        {CAPABILITIES.map(item => {
          const Icon = item.icon
          return (
            <article key={item.title} className="capability-card">
              <div className="capability-icon">
                <Icon size={22} />
              </div>
              <h2>{item.title}</h2>
              <p>{item.text}</p>
              <button className="text-action" onClick={() => onNavigate(item.target)}>
                {item.action}
                <ArrowRight size={16} />
              </button>
            </article>
          )
        })}
      </section>

      <section className="ops-band">
        <div>
          <span className="eyebrow eyebrow--dark">
            <ShieldCheck size={16} />
            Operations ready
          </span>
          <h2>Designed for inspectable cloud runs</h2>
        </div>
        <p>
          The portal mirrors the pipeline shape: uploads enter the lake, workflow
          state stays visible, and AI answers remain connected to Athena results.
        </p>
      </section>
    </div>
  )
}
