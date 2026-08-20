type PageIntroProps = {
  title?: string
  description: string
}

export function PageIntro({ title, description }: PageIntroProps) {
  return (
    <div className="flex flex-col gap-1">
      {title ? (
        <h2 className="text-lg font-medium tracking-tight">{title}</h2>
      ) : null}
      <p className="max-w-2xl text-sm leading-relaxed text-muted-foreground">{description}</p>
    </div>
  )
}
